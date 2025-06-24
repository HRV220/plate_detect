import logging
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
    version="2.0.0", # <--- Повышаем версию, так как это мажорное изменение API
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
    logger.exception(f"Необработанная ошибка: {request.method} {request.url}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера."},
    )

# 5. События жизненного цикла
@app.on_event("startup")
async def on_startup():
    logger.info("--- Сервис запускается (режим 'in-memory processing') ---")
    try:
        dependencies.coverer = await create_number_plate_coverer()
    except Exception:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать сервис.")

@app.on_event("shutdown")
def on_shutdown():
    logger.info("--- Сервис останавливается ---")

# 6. Подключение роутеров
# Переименовываем тег для ясности
app.include_router(api_v1_router.router, prefix=settings.API_V1_STR, tags=["Image Processing"]) 
app.include_router(utils_router.router)
