import logging
import sys  # <--- 1. ДОБАВИТЬ ЭТОТ ИМПОРТ
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.middleware import MaxRequestSizeMiddleware
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.v1 import endpoints as api_v1_router
from app.api.utils import endpoints as utils_router
from app.core.processor import create_number_plate_coverer
from app import dependencies

# 1. Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# 2. Определение метаданных
tags_metadata = [
    {"name": "Image Processing", "description": "Основной эндпоинт для обработки изображений."},
    {"name": "Monitoring", "description": "Эндпоинты для проверки состояния сервиса."},
]

# 3. Создание экземпляра FastAPI
app = FastAPI(
    title="Сервис для анонимизации номерных знаков",
    description="API для обработки изображений 'на лету'. Принимает пачку изображений и возвращает ZIP-архив с результатами.",
    version="2.0.0",
    openapi_tags=tags_metadata,
    docs_url=None,
    redoc_url=None
)

# 4. Настройка Middleware
app.add_middleware(
    MaxRequestSizeMiddleware,
    max_size_bytes=settings.MAX_REQUEST_SIZE_MB * 1024 * 1024
)

# Глобальный обработчик исключений
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Эта версия уже правильная: logger.exception логирует полный stack trace.
    logger.exception(f"Перехвачена необработанная ошибка для запроса: {request.method} {request.url}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера."},
    )

# 5. События жизненного цикла
@app.on_event("startup")
async def on_startup():
    """
    Асинхронное событие при запуске приложения.
    Инициализирует критически важные зависимости, такие как ML-модель.
    """
    logger.info("--- Сервис запускается (режим 'in-memory processing') ---")
    try:
        dependencies.coverer = await create_number_plate_coverer()
        logger.info("Ключевые зависимости успешно инициализированы.")
    except Exception:
        # 2. ИСПРАВЛЕНИЕ: Аварийное завершение при ошибке инициализации.
        # Это критически важно для продакшена. Если модель не загрузилась,
        # сервис не должен делать вид, что он работает.
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать сервис. Завершение работы.")
        # Выход с ненулевым кодом сообщит системе оркестрации (Docker, Kubernetes),
        # что контейнер неисправен и его нужно перезапустить.
        sys.exit(1)

@app.on_event("shutdown")
def on_shutdown():
    """Синхронное событие при остановке приложения."""
    logger.info("--- Сервис останавливается ---")

# 6. Подключение роутеров
app.include_router(api_v1_router.router, prefix=settings.API_V1_STR, tags=["Image Processing"])
app.include_router(utils_router.router)