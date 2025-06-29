# app/core/config.py
import os
from typing import List, Optional # <-- Добавьте Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Пути к ресурсам
    MODEL_PATH: str = "models/best.pt"
    COVER_IMAGE_PATH: str = "static/cover.png"
    TASKS_STORAGE_PATH: str = "tasks_storage"
    
    # Настройки валидации запросов
    MAX_REQUEST_SIZE_MB: int = 100 # Максимальный общий размер запроса
    MAX_FILES_PER_REQUEST: int = 50 # Максимальное количество файлов в одном запросе
    MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024 # Максимальный размер одного файла (20 MB)
    
    # Разрешенные MIME-типы
    ALLOWED_MIME_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]
    
    # Префикс для API (для версионирования)
    API_V1_STR: str = "/api/v1"

    # Настройки устройства для ML модели
    # Можно будет легко переключить на 'cuda' через переменную окружения в Docker
    PROCESSING_DEVICE: str = os.getenv("PROCESSING_DEVICE", "cpu")

    # --- Настройки производительности ---
    # !!! ДОБАВЛЕНА НЕДОСТАЮЩАЯ НАСТРОЙКА !!!
    # Определяет, сколько изображений будет обрабатываться моделью за один раз (батч).
    # Большие значения могут ускорить обработку на GPU, но требуют больше видеопамяти.
    PROCESSING_BATCH_SIZE: int = 16

    # --- Настройки очистки ---
    # Время жизни директории с задачей в часах. По истечении этого времени
    # директория будет автоматически удалена фоновой задачей.
    TASK_STORAGE_TTL_HOURS: int = 48 # 3 дня

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = 6379

    # URL для отправки JSON-уведомления о завершении задачи.
    BACKEND_CALLBACK_URL: Optional[str] = os.getenv("BACKEND_CALLBACK_URL")

    # URL на бэкенде, который будет принимать multipart/form-data запросы с файлами.
    # Если эта переменная не установлена, файлы отправляться не будут.
    BACKEND_UPLOAD_URL: Optional[str] = os.getenv("BACKEND_UPLOAD_URL")

    class Config:
        case_sensitive = True

# Создаем единственный экземпляр настроек, который будет использоваться во всем приложении
settings = Settings()