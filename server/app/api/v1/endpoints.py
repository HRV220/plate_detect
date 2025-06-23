import logging
from typing import List

from fastapi import (
    APIRouter, 
    File, 
    UploadFile, 
    HTTPException, 
    BackgroundTasks, 
    Path as FastAPIPath, 
    Request
)

from app.api.v1 import schemas
from app.services import task_manager
from app.core.config import settings # <--- Импортируем наши настройки

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post(
    "/process-task/", 
    response_model=schemas.TaskResponse, 
    status_code=202,
    summary="Создать задачу на обработку изображений"
)
async def create_task(
    request: Request,
    background_tasks: BackgroundTasks, 
    files: List[UploadFile] = File(
        ..., 
        description="Список изображений (JPEG, PNG, WebP) для обработки."
    )
):
    """
    Создает асинхронную задачу на обработку пачки изображений.

    - **Принимает:** Список файлов.
    - **Возвращает:** Мгновенный ответ с `task_id`.
    - **В фоне:** Сохраняет файлы и запускает их обработку.
    """
    client_host = request.client.host
    logger.info(f"Получен запрос на создание задачи от {client_host} с {len(files)} файлами.")

    # --- НАЧАЛО БЛОКА ВАЛИДАЦИИ ВХОДНЫХ ДАННЫХ ---

    # 1. Проверка общего количества файлов в запросе
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        msg = f"Превышен лимит на количество файлов в запросе ({len(files)} > {settings.MAX_FILES_PER_REQUEST})."
        logger.warning(f"{msg} (Клиент: {client_host})")
        raise HTTPException(status_code=413, detail=msg) # 413 Payload Too Large

    # 2. Проверка каждого файла индивидуально (размер и MIME-тип)
    for file in files:
        # Проверка размера файла. file.size доступен после того, как файл начал читаться.
        # FastAPI достаточно умен, чтобы предоставить этот атрибут.
        if file.size > settings.MAX_FILE_SIZE_BYTES:
            msg = f"Файл '{file.filename}' слишком большой ({file.size / 1024 / 1024:.2f} MB > {settings.MAX_FILE_SIZE_BYTES / 1024 / 1024:.2f} MB)."
            logger.warning(f"{msg} (Клиент: {client_host})")
            raise HTTPException(status_code=413, detail=msg)
        
        # Проверка MIME-типа файла
        if file.content_type not in settings.ALLOWED_MIME_TYPES:
            msg = f"Неподдерживаемый тип файла '{file.filename}' ({file.content_type}). Разрешены: {', '.join(settings.ALLOWED_MIME_TYPES)}."
            logger.warning(f"{msg} (Клиент: {client_host})")
            raise HTTPException(status_code=415, detail=msg) # 415 Unsupported Media Type
            
    # --- КОНЕЦ БЛОКА ВАЛИДАЦИИ ---

    # Проверка доступности сервиса (бизнес-логика)
    if not task_manager.SERVICE_AVAILABLE:
        logger.error(f"Отклонен запрос от {client_host}: сервис недоступен из-за ошибки инициализации.")
        raise HTTPException(
            status_code=503, 
            detail="Сервис временно недоступен. Пожалуйста, попробуйте позже."
        )
    
    # Делегируем всю работу сервисному слою
    task_id = await task_manager.create_processing_task(background_tasks, files)
    
    logger.info(f"Задача {task_id} успешно создана для клиента {client_host}.")
    
    return schemas.TaskResponse(task_id=task_id)


@router.get(
    "/task-status/{task_id}", 
    response_model=schemas.TaskStatusResponse,
    summary="Получить статус задачи"
)
async def read_task_status(
    request: Request,
    task_id: str = FastAPIPath(..., description="ID задачи, полученный при её создании.")
):
    """
    Получает текущий статус и результаты выполнения задачи.

    Опрашивайте этот эндпоинт периодически, пока статус не станет `completed` или `failed`.
    """
    client_host = request.client.host
    logger.info(f"Запрос статуса для задачи {task_id} от {client_host}.")
    
    task_status = task_manager.get_task_status(task_id)

    if task_status is None:
        logger.warning(f"Запрошена несуществующая задача {task_id} от {client_host}.")
        raise HTTPException(status_code=404, detail=f"Задача с ID '{task_id}' не найдена.")
    
    logger.info(f"Отправлен статус '{task_status['status']}' для задачи {task_id}.")
    return task_status