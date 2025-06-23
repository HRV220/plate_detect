# app/api/v1/endpoints.py
from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks, Path as FastAPIPath

from app.api.v1 import schemas
from app.services import task_manager

router = APIRouter()

@router.post("/process-task/", response_model=schemas.TaskResponse, status_code=202)
async def create_task(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    """Создает задачу на обработку пачки изображений."""
    if not task_manager.SERVICE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Сервис недоступен из-за ошибки инициализации.")
    
    task_id = await task_manager.create_processing_task(background_tasks, files)
    return {"task_id": task_id}

@router.get("/task-status/{task_id}", response_model=schemas.TaskStatusResponse)
async def read_task_status(task_id: str = FastAPIPath(..., description="ID задачи.")):
    """Получает статус и результаты выполнения задачи."""
    task = task_manager.get_task_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена.")
    return task