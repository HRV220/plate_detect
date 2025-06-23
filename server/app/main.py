# server/app/main.py

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.v1 import endpoints as api_v1_router
from app.api.utils import endpoints as utils_router

# 1. Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# 2. Определение метаданных (оставляем, это полезно)
tags_metadata = [
    {"name": "API V1", "description": "Основные эндпоинты для работы с задачами."},
    {"name": "Monitoring", "description": "Эндпоинты для проверки состояния сервиса."},
]

# 3. Создание экземпляра FastAPI
app = FastAPI(
    title="Сервис для анонимизации номерных знаков",
    description="API для асинхронной обработки изображений.",
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url=None, 
    redoc_url=None
)

# 4. Глобальный обработчик исключений (оставляем, это важно для server-to-server)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Необработанная ошибка: {request.method} {request.url}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера."},
    )

# 5. События жизненного цикла (оставляем)
@app.on_event("startup")
def on_startup():
    logger.info("--- Сервис запускается ---")
    logger.info(f"Настройки: DEVICE={settings.PROCESSING_DEVICE}, MODEL={settings.MODEL_PATH}")
    try:
        Path(settings.TASKS_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        logger.info(f"Хранилище задач готово: {settings.TASKS_STORAGE_PATH}")
    except Exception:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось создать директорию для хранения задач.")

@app.on_event("shutdown")
def on_shutdown():
    logger.info("--- Сервис останавливается ---")

# 6. Подключение роутеров
app.include_router(api_v1_router.router, prefix=settings.API_V1_STR, tags=["API V1"])
app.include_router(utils_router.router)

# 7. Монтирование статических файлов
app.mount(
    f"/{settings.TASKS_STORAGE_PATH}",
    StaticFiles(directory=settings.TASKS_STORAGE_PATH, html=False),
    name="results"
)