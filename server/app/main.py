# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1 import endpoints as v1_endpoints

app = FastAPI(title="Сервис обработки номеров")

# Подключаем роутер с нашими эндпоинтами
app.include_router(v1_endpoints.router, prefix=settings.API_V1_STR, tags=["API V1"])

# Монтируем директорию для скачивания результатов
app.mount(
    f"/{settings.TASKS_STORAGE_PATH}",
    StaticFiles(directory=settings.TASKS_STORAGE_PATH),
    name="results"
)

@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Welcome to the Number Plate Coverer API!", "docs": "/docs"}