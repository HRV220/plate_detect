# server/app/main.py

import logging
from pathlib import Path
import redis.asyncio as redis

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# --- ДОБАВЛЕНЫ ИМПОРТЫ ДЛЯ ПЛАНИРОВЩИКА ---
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.middleware import MaxRequestSizeMiddleware
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.v1 import endpoints as api_v1_router
from app.api.utils import endpoints as utils_router
from app.core.processor import create_number_plate_coverer
# --- ДОБАВЛЕН ИМПОРТ УБОРЩИКА ---
from app.background.cleaner import cleanup_old_tasks
from app import dependencies


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
    description="API для асинхронной обработки изображений с использованием Redis и автоочисткой.",
    version="1.2.0", # Версия обновлена
    openapi_tags=tags_metadata,
    docs_url=None,
    redoc_url=None
)

# --- ДОБАВЛЕНО: Глобальный экземпляр планировщика ---
scheduler = AsyncIOScheduler(timezone="UTC")


# 4. НАСТРОЙКА MIDDLEWARE
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
    """
    Выполняется при запуске приложения. Инициализирует все зависимости и
    запускает фоновый планировщик для очистки старых задач.
    """
    logger.info("--- Сервис запускается ---")
    try:
        # Инициализация клиента Redis
        logger.info(f"Подключение к Redis по адресу {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        dependencies.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True
        )
        await dependencies.redis_client.ping()
        logger.info("Успешно подключено к Redis.")

        # Инициализация ML-процессора
        logger.info(f"Загрузка модели '{settings.MODEL_PATH}' на устройство '{settings.PROCESSING_DEVICE}'...")
        dependencies.coverer = await create_number_plate_coverer()

        # Создание директории для хранения задач
        Path(settings.TASKS_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        logger.info(f"Хранилище задач готово: {settings.TASKS_STORAGE_PATH}")

        # --- ДОБАВЛЕНО: Запуск планировщика ---
        # Добавляем задачу очистки, которая будет выполняться каждый час.
        scheduler.add_job(cleanup_old_tasks, 'interval', hours=1, id="cleanup_job")
        scheduler.start()
        logger.info("Планировщик очистки старых задач запущен. Проверка будет выполняться каждый час.")

    except redis.exceptions.ConnectionError:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Redis.")
        dependencies.redis_client = None
        dependencies.coverer = None
    except Exception:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать сервис.")
        dependencies.redis_client = None
        dependencies.coverer = None


@app.on_event("shutdown")
async def on_shutdown():
    """
    Выполняется при остановке приложения. Корректно закрывает соединения
    и останавливает планировщик.
    """
    logger.info("--- Сервис останавливается ---")

    # --- ДОБАВЛЕНО: Остановка планировщика ---
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Планировщик очистки остановлен.")

    if dependencies.redis_client:
        await dependencies.redis_client.close()
        logger.info("Соединение с Redis закрыто.")


# 6. Подключение роутеров
app.include_router(api_v1_router.router, prefix=settings.API_V1_STR, tags=["API V1"])
app.include_router(utils_router.router)


# 7. Монтирование статических файлов для раздачи результатов
app.mount(
    f"/{settings.TASKS_STORAGE_PATH}",
    StaticFiles(directory=settings.TASKS_STORAGE_PATH, html=False),
    name="results"
)