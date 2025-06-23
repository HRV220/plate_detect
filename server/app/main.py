import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.api.v1 import endpoints as v1_endpoints

# 1. Настраиваем логирование в самом начале
setup_logging()
logger = logging.getLogger(__name__)

# 2. Определяем метаданные для красивой документации
tags_metadata = [
    {
        "name": "API V1",
        "description": "Основные эндпоинты для работы с задачами по обработке изображений.",
    },
    {
        "name": "Root",
        "description": "Эндпоинты для проверки состояния сервиса.",
    },
]

# 3. Создаем экземпляр FastAPI с подробным описанием
app = FastAPI(
    title="Сервис для анонимизации номерных знаков",
    description="""
API для асинхронной обработки изображений. 
Позволяет загружать пачку изображений, находить на них автомобильные номера 
и накладывать кастомную заглушку.

**Рабочий процесс:**
1. Отправьте изображения на эндпоинт `/api/v1/process-task/`.
2. Получите `task_id` в ответе.
3. Периодически опрашивайте эндпоинт `/api/v1/task-status/{task_id}`.
4. Когда статус станет `completed`, скачайте файлы по полученным URL.
    """,
    version="1.0.0",
    contact={
        "name": "Ваше Имя / Название Компании",
        "url": "http://example.com", # Замените на ваш сайт
        "email": "youremail@example.com", # Замените на ваш email
    },
    openapi_tags=tags_metadata
)

# 4. Используем событие on_startup для логирования при старте
@app.on_event("startup")
def on_startup():
    """Выполняется один раз при запуске сервера."""
    logger.info("Сервис запускается...")
    logger.info(f"Настройки: DEVICE={settings.PROCESSING_DEVICE}, MODEL={settings.MODEL_PATH}")
    # Проверяем наличие папки для задач, создаем если ее нет
    try:
        Path(settings.TASKS_STORAGE_PATH).mkdir(exist_ok=True)
        logger.info(f"Хранилище задач готово по пути: {settings.TASKS_STORAGE_PATH}")
    except Exception as e:
        logger.error(f"Не удалось создать директорию для хранения задач: {e}")


# 5. Подключаем роутер с нашими эндпоинтами
app.include_router(v1_endpoints.router, prefix=settings.API_V1_STR, tags=["API V1"])

# 6. Монтируем директорию для скачивания результатов
app.mount(
    f"/{settings.TASKS_STORAGE_PATH}",
    StaticFiles(directory=settings.TASKS_STORAGE_PATH),
    name="results"
)

# 7. Добавляем корневой эндпоинт для проверки работы
@app.get("/", tags=["Root"])
def read_root():
    """
    Корневой эндпоинт. Позволяет быстро проверить, что сервис запущен и отвечает.
    """
    return {"message": "Welcome to the Number Plate Coverer API!", "docs": "/docs"}

# Добавляем импорт Path для on_startup
from pathlib import Path