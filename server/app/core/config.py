# app/core/config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Пути к ресурсам
    MODEL_PATH: str = "models/best.pt"
    COVER_IMAGE_PATH: str = "static/cover.png"
    TASKS_STORAGE_PATH: str = "tasks_storage"
    
    # Настройки устройства для ML модели
    # Можно будет легко переключить на 'cuda' через переменную окружения в Docker
    PROCESSING_DEVICE: str = os.getenv("PROCESSING_DEVICE", "cpu")

    # Префикс для API (для версионирования)
    API_V1_STR: str = "/api/v1"

    class Config:
        case_sensitive = True

# Создаем единственный экземпляр настроек, который будет использоваться во всем приложении
settings = Settings()