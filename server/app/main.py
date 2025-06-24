# server/app/main.py

import logging
from pathlib import Path
import redis.asyncio as redis # Используем асинхронный клиент для Redis

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.middleware import MaxRequestSizeMiddleware
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.v1 import endpoints as api_v1_router
from app.api.utils import endpoints as utils_router
from app.core.processor import create_number_plate_coverer
from app import dependencies

# --- УДАЛЕНО: Больше не нужен отдельный планировщик ---
# from app.background import scheduler as app_scheduler


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
    description="API для асинхронной обработки изображений с использованием Redis для управления задачами.",
    version="1.1.0", # Версию можно обновить, так как произошли существенные изменения
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
@app.on_event("startup")
async def on_startup():
    """
    Выполняется при запуске приложения.
    Инициализирует подключение к Redis и загружает ML-модель.
    """
    logger.info("--- Сервис запускается ---")
    try:
        # --- ДОБАВЛЕНО: Инициализация клиента Redis ---
        logger.info(f"Подключение к Redis по адресу {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        dependencies.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            decode_responses=True # Важно для получения строк, а не байтов
        )
        await dependencies.redis_client.ping() # Проверяем, что соединение установлено
        logger.info("Успешно подключено к Redis.")

        # Асинхронно инициализируем ML-процессор
        logger.info(f"Загрузка модели '{settings.MODEL_PATH}' на устройство '{settings.PROCESSING_DEVICE}'...")
        dependencies.coverer = await create_number_plate_coverer()

        # Создаем директорию для хранения результатов задач
        Path(settings.TASKS_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        logger.info(f"Хранилище задач готово: {settings.TASKS_STORAGE_PATH}")

        # --- УДАЛЕНО: Инициализация планировщика больше не нужна ---
        # app_scheduler.initialize_scheduler()

    except redis.exceptions.ConnectionError:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Redis.")
        # Сбрасываем зависимости, чтобы is_service_available() возвращал False
        dependencies.redis_client = None
        dependencies.coverer = None
    except Exception:
        logger.exception("КРИТИЧЕСКАЯ ОШИБКА: Не удалось инициализировать сервис.")
        dependencies.redis_client = None
        dependencies.coverer = None

@app.on_event("shutdown")
async def on_shutdown(): # <-- Функция стала асинхронной
    """
    Выполняется при остановке приложения.
    Корректно закрывает соединение с Redis.
    """
    logger.info("--- Сервис останавливается ---")
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