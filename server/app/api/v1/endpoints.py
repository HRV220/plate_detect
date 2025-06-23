import logging
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Path as FastAPIPath, Request

from app.api.v1 import schemas
from app.services import task_manager

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/process-task/", response_model=schemas.TaskResponse, status_code=202)
async def create_task(
    request: Request, # Добавляем объект Request для получения информации о клиенте
    background_tasks: BackgroundTasks, 
    files: List[UploadFile] = File(...)
):
    """Создает задачу на обработку пачки изображений."""
    client_host = request.client.host
    logger.info(f"Получен запрос на создание задачи от {client_host} с {len(files)} файлами.")

    if not task_manager.SERVICE_AVAILABLE:
        # Логируем ошибку, прежде чем вернуть ее клиенту
        logger.error(f"Попытка создать задачу, когда сервис недоступен. Запрос от {client_host}.")
        raise HTTPException(status_code=503, detail="Сервис недоступен из-за ошибки инициализации.")
    
    task_id = await task_manager.create_processing_task(background_tasks, files)
    logger.info(f"Задача {task_id} успешно создана и добавлена в фон для клиента {client_host}.")
    
    return {"task_id": task_id}

@router.get("/task-status/{task_id}", response_model=schemas.TaskStatusResponse)
async def read_task_status(
    request: Request, # Добавляем объект Request
    task_id: str = FastAPIPath(..., description="ID задачи.")
):
    """Получает статус и результаты выполнения задачи."""
    client_host = request.client.host
    logger.info(f"Получен запрос статуса для задачи {task_id} от {client_host}.")
    
    task = task_manager.get_task_status(task_id)
    if task is None:
        logger.warning(f"Запрошена несуществующая задача {task_id} от клиента {client_host}.")
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    
    logger.info(f"Отправлен статус '{task['status']}' для задачи {task_id} клиенту {client_host}.")
    return task