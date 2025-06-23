# server/app/core/middleware.py

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.core.config import settings

logger = logging.getLogger(__name__)

class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_size_bytes: int):
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(
        self, request: Request, call_next: Callable
    ):
        content_length_header = request.headers.get("content-length")
        
        if content_length_header:
            try:
                content_length = int(content_length_header)
                if content_length > self.max_size_bytes:
                    return self._error_response(request, content_length)
            except (ValueError, TypeError):
                logger.warning(f"Некорректный заголовок Content-Length от клиента {request.client.host}")
                pass

        response = await call_next(request)
        return response

    def _error_response(self, request: Request, received_size: int) -> JSONResponse:
        """Формирует и логирует ответ с ошибкой."""
        client_host = request.client.host
        error_message = (
            f"Запрос отклонен: размер тела ({received_size / 1024 / 1024:.2f} MB) "
            f"превышает лимит ({self.max_size_bytes / 1024 / 1024:.2f} MB)."
        )
        logger.warning(f"{error_message} (Клиент: {client_host})")
        return JSONResponse(
            status_code=413,  # 413 Payload Too Large
            content={"detail": error_message}
        )