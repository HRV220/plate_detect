# app/core/config.py
import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Пути к ресурсам
    MODEL_PATH: str = "models/best.pt"
    COVER_IMAGE_PATH: str = "static/cover.png"
    
    # Настройки валидации запросов
    MAX_REQUEST_SIZE_MB: int = 100 # Максимальный общий размер запроса
    MAX_FILES_PER_REQUEST: int = 50
    MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024 # 20 MB
    
    # Разрешенные MIME-типы
    ALLOWED_MIME_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]
    
    # Префикс для API
    API_V1_STR: str = "/api/v1"

    # Настройки устройства для ML модели
    PROCESSING_DEVICE: str = os.getenv("PROCESSING_DEVICE", "cpu")

    # Настройки производительности
    PROCESSING_BATCH_SIZE: int = 16

    class Config:
        case_sensitive = True

settings = Settings()