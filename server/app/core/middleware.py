# server/app/core/middleware.py

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    """
    Middleware для ограничения максимального размера тела HTTP-запроса.

    Это middleware защищает приложение от атак типа "отказ в обслуживании" (DoS),
    вызванных отправкой слишком больших тел запросов. Оно обрабатывает как
    запросы с заголовком 'Content-Length', так и потоковые запросы с
    'Transfer-Encoding: chunked'.
    """

    def __init__(self, app: ASGIApp, max_size_bytes: int):
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """
        Основной метод middleware, обрабатывающий входящий запрос.
        """
        # 1. Быстрая проверка по Content-Length (если он есть)
        # Это самый дешевый способ отсечь большие запросы без чтения тела.
        if "content-length" in request.headers:
            try:
                content_length = int(request.headers["content-length"])
                if content_length > self.max_size_bytes:
                    return self._error_response(
                        request=request,
                        reason=f"Заголовок Content-Length ({content_length} байт) превышает лимит."
                    )
            except (ValueError, TypeError):
                # Если заголовок некорректен, мы не можем ему доверять.
                # Логируем и переходим к потоковой проверке ниже.
                logger.warning(
                    f"Некорректный заголовок Content-Length от клиента {request.client.host}: "
                    f"'{request.headers['content-length']}'"
                )

        # 2. Обработка потоковых запросов (chunked) или запросов без Content-Length.
        # Это единственный надежный способ проверить реальный размер тела.
        transfer_encoding = request.headers.get("transfer-encoding")
        if transfer_encoding and "chunked" in transfer_encoding.lower():
            try:
                # Читаем тело по частям, чтобы не загружать все в память сразу.
                body_chunks = []
                received_size = 0
                async for chunk in request.stream():
                    received_size += len(chunk)
                    if received_size > self.max_size_bytes:
                        return self._error_response(
                            request=request,
                            reason=f"Размер тела запроса в потоке превысил лимит ({self.max_size_bytes} байт)."
                        )
                    body_chunks.append(chunk)
                
                # Если все в порядке, мы "собираем" тело и передаем его дальше.
                # Важно: stream() можно прочитать только один раз. Мы его "израсходовали",
                # поэтому должны подменить ASGI receive, чтобы передать уже прочитанное тело
                # следующему обработчику в цепочке.
                
                # Создаем новый "receive", который вернет собранное тело.
                scope = request.scope
                
                async def receive() -> dict:
                    return {"type": "http.request", "body": b"".join(body_chunks), "more_body": False}
                
                # Создаем новый экземпляр Request с нашим кастомным receive.
                new_request = Request(scope, receive)
                return await call_next(new_request)

            except Exception as e:
                # На случай разрыва соединения или других ошибок при чтении потока.
                logger.warning(f"Ошибка при чтении потокового запроса от {request.client.host}: {e}")
                return JSONResponse(
                    status_code=400, # Bad Request
                    content={"detail": "Ошибка при чтении тела запроса."}
                )

        # 3. Если это не chunked и Content-Length в норме (или отсутствует), пропускаем дальше.
        return await call_next(request)

    def _error_response(self, request: Request, reason: str) -> JSONResponse:
        """
        Формирует, логирует и возвращает ответ с ошибкой 413 Payload Too Large.
        """
        client_host = request.client.host if request.client else "unknown"
        error_message = (
            f"Запрос отклонен: размер тела превышает установленный лимит "
            f"({self.max_size_bytes / 1024 / 1024:.2f} MB)."
        )
        logger.warning(f"{error_message} (Клиент: {client_host}, Причина: {reason})")
        return JSONResponse(
            status_code=413,  # Payload Too Large
            content={"detail": error_message}
        )