# server/app/main.py

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.middleware import MaxRequestSizeMiddleware
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.v1 import endpoints as api_v1_router
from app.api.utils import endpoints as utils_router
from app.core.processor import create_number_plate_coverer  # <-- ИЗМЕНЕНИЕ: Импортируем нашу фабрику
from app import dependencies                            # <-- ИЗМЕНЕНИЕ: Импортируем новый модуль
from app.background import scheduler as app_scheduler # <-- ИЗМЕНЕНИЕ: импортируем наш новый модуль


# 1. Настройка логирования
setup_logging()
logger = logging.getLogger(__name__)

# 2. Определение метаданных
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

# 4. НАСТРОЙКА MIDDLEWARE (Промежуточное ПО)
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
# --- ИЗМЕНЕНИЕ: Событие startup теперь асинхронное, чтобы не блокировать запуск ---
@app.on_event("startup")
async def on_startup():
    logger.info("--- Сервис запускается ---")
    logger.info(f"Настройки: DEVICE={settings.PROCESSING_DEVICE}, MODEL={settings.MODEL_PATH}")
    try:
        # Асинхронно инициализируем наш процессор и сохраняем его
        # в общем модуле для зависимостей.
        dependencies.coverer = await create_number_plate_coverer()
        
        # Создаем директорию для хранения задач (быстрая операция, можно оставить синхронной)
        Path(settings.TASKS_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        logger.info(f"Хранилище задач готово: {settings.TASKS_STORAGE_PATH}")
        app_scheduler.initialize_scheduler()

    except Exception:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать сервис или хранилище.")
        # В случае ошибки `dependencies.coverer` останется None,
        # и сервис будет корректно сообщать о своей недоступности.

@app.on_event("shutdown")
def on_shutdown():
    logger.info("--- Сервис останавливается ---")
    app_scheduler.stop_scheduler()
# 6. Подключение роутеров
app.include_router(api_v1_router.router, prefix=settings.API_V1_STR, tags=["API V1"])
app.include_router(utils_router.router)

# 7. Монтирование статических файлов
app.mount(
    f"/{settings.TASKS_STORAGE_PATH}",
    StaticFiles(directory=settings.TASKS_STORAGE_PATH, html=False),
    name="results"
)