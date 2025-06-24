# server/app/core/middleware.py

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    """
    Middleware для ограничения максимального размера тела HTTP-запроса.

    Защищает приложение от DoS-атак, вызванных отправкой слишком больших
    запросов. Middleware работает, проверяя заголовок 'Content-Length'.
    """

    def __init__(self, app: ASGIApp, max_size_bytes: int):
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """
        Основной метод middleware, обрабатывающий входящий запрос.
        """
        # Мы проверяем только запросы, которые могут иметь тело.
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # 1. Проверяем наличие заголовка Content-Length
        content_length_header = request.headers.get("content-length")
        
        if not content_length_header:
            # Отклоняем запрос, если длина тела неизвестна. Это самая безопасная стратегия.
            client_host = request.client.host if request.client else "unknown"
            logger.warning(f"Запрос от {client_host} отклонен: отсутствует заголовок Content-Length.")
            return JSONResponse(
                status_code=411,  # 411 Length Required
                content={"detail": "Заголовок Content-Length является обязательным."}
            )

        # 2. Проверяем значение заголовка
        try:
            content_length = int(content_length_header)
            if content_length > self.max_size_bytes:
                # Если размер превышает лимит, формируем и возвращаем ошибку
                return self._error_response(request, content_length)
        except (ValueError, TypeError):
            # Если заголовок не является корректным числом, это плохой запрос.
            client_host = request.client.host if request.client else "unknown"
            logger.warning(f"Некорректный заголовок Content-Length '{content_length_header}' от клиента {client_host}.")
            return JSONResponse(
                status_code=400, # 400 Bad Request
                content={"detail": "Некорректное значение заголовка Content-Length."}
            )

        # 3. Если все проверки пройдены, передаем запрос дальше.
        return await call_next(request)


    def _error_response(self, request: Request, received_size: int) -> JSONResponse:
        """
        Формирует, логирует и возвращает ответ с ошибкой 413 Payload Too Large.
        """
        client_host = request.client.host if request.client else "unknown"
        error_message = (
            f"Размер тела запроса ({received_size / 1024 / 1024:.2f} MB) "
            f"превышает установленный лимит ({self.max_size_bytes / 1024 / 1024:.2f} MB)."
        )
        logger.warning(f"Запрос от {client_host} отклонен. Причина: {error_message}")
        return JSONResponse(
            status_code=413,  # Payload Too Large
            content={"detail": error_message}
        )