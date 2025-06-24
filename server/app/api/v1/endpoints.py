import logging
import io
from zipfile import ZipFile, ZIP_DEFLATED
from typing import List
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, Request, HTTPException
from fastapi.responses import StreamingResponse
import numpy as np
from PIL import Image, UnidentifiedImageError
import cv2

from app.core.config import settings
from app import dependencies # Импортируем для доступа к 'coverer'

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
    "/process-images/", 
    summary="Обработать изображения и вернуть ZIP-архив",
    response_description="ZIP-архив с обработанными изображениями в формате JPEG.",
    # Убираем response_model, так как возвращаем файл
)
async def process_images_in_memory(
    request: Request,
    files: List[UploadFile] = File(..., description="Изображения для обработки (JPEG, PNG, WebP).")
):
    """
    Принимает список изображений, обрабатывает их "на лету" в памяти
    и возвращает ZIP-архив с результатами.
    
    Этот эндпоинт является синхронным с точки зрения клиента: он будет ждать,
    пока все изображения не будут обработаны.
    """
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Получен запрос на обработку {len(files)} файлов от {client_host}.")

    if not dependencies.coverer:
        raise HTTPException(status_code=503, detail="Сервис временно недоступен.")

    # --- Валидация входных данных ---
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=413, detail=f"Слишком много файлов. Лимит: {settings.MAX_FILES_PER_REQUEST}.")

    images_to_process = []
    original_filenames = []

    # 1. Чтение и валидация файлов в памяти
    for file in files:
        if file.size > settings.MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"Файл '{file.filename}' слишком большой.")
        if file.content_type not in settings.ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=415, detail=f"Неподдерживаемый тип файла: '{file.filename}'.")
        
        try:
            contents = await file.read()
            pil_image = Image.open(io.BytesIO(contents))
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            image_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            images_to_process.append(image_bgr)
            original_filenames.append(Path(file.filename).stem)
        except UnidentifiedImageError:
            logger.warning(f"Файл {file.filename} от {client_host} не является изображением. Пропускаем.")
        except Exception:
            logger.exception(f"Ошибка при чтении файла {file.filename} от {client_host}.")

    if not images_to_process:
        raise HTTPException(status_code=400, detail="Не было предоставлено ни одного валидного изображения для обработки.")

    # 2. Пакетная обработка в памяти
    processed_images = dependencies.coverer.cover_plates_batch(
        images_to_process, 
        batch_size=settings.PROCESSING_BATCH_SIZE
    )

    # 3. Создание ZIP-архива в памяти
    zip_buffer = io.BytesIO()
    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
        for i, image_array in enumerate(processed_images):
            # Кодируем обработанное изображение в формат JPEG в памяти
            success, image_bytes = cv2.imencode(".jpg", image_array, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            if not success:
                logger.error(f"Не удалось закодировать обработанный файл {original_filenames[i]}")
                continue
            
            # Добавляем файл в zip-архив
            filename = f"covered_{original_filenames[i]}.jpg"
            zip_file.writestr(filename, image_bytes.tobytes())

    zip_buffer.seek(0)
    
    logger.info(f"Обработка {len(files)} файлов для {client_host} завершена. Отправка ZIP-архива.")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=processed_images.zip"}
    )