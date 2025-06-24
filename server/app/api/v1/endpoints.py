import logging
import io
from zipfile import ZipFile, ZIP_DEFLATED
from typing import List, Tuple
from pathlib import Path

from fastapi import APIRouter, File, UploadFile, Request, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
import numpy as np
from PIL import Image, UnidentifiedImageError
import cv2

from app.core.config import settings
from app import dependencies

# Использование __name__ — лучшая практика для именования логгеров
logger = logging.getLogger(__name__)
router = APIRouter()


def _process_and_zip_sync(
    files_data: List[Tuple[str, bytes]], 
    client_host: str
) -> io.BytesIO | None:
    """
    Синхронная "worker" функция, которая выполняет всю тяжелую работу.
    Она предназначена для запуска в отдельном потоке через run_in_threadpool.
    
    Эта функция выполняет:
    1. Декодирование и предобработку изображений.
    2. Пакетную обработку моделью.
    3. Кодирование результатов и упаковку в ZIP-архив.
    
    Args:
        files_data: Список кортежей, где каждый кортеж - (имя_файла, байты_файла).
        client_host: IP клиента для логирования.

    Returns:
        Буфер BytesIO с ZIP-архивом или None, если не было валидных изображений.
    """
    images_to_process = []
    original_filenames = []

    # --- 1. Декодирование и предобработка в памяти ---
    for filename, contents in files_data:
        try:
            pil_image = Image.open(io.BytesIO(contents))
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # Конвертация в формат, который использует модель (BGR для OpenCV)
            image_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            images_to_process.append(image_bgr)
            original_filenames.append(Path(filename).stem)
        except UnidentifiedImageError:
            logger.warning(f"Файл {filename} от {client_host} не является изображением. Пропускаем.")
        except Exception:
            logger.exception(f"Ошибка при чтении или обработке файла {filename} от {client_host}.")

    if not images_to_process:
        logger.warning(f"Для клиента {client_host} не было предоставлено валидных изображений.")
        return None

    # --- 2. Пакетная обработка моделью (тяжелые вычисления) ---
    processed_images = dependencies.coverer.cover_plates_batch(
        images_to_process, 
        batch_size=settings.PROCESSING_BATCH_SIZE
    )

    # --- 3. Создание ZIP-архива в памяти ---
    zip_buffer = io.BytesIO()
    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as zip_file:
        for i, image_array in enumerate(processed_images):
            # Кодируем обработанное изображение в формат JPEG в памяти
            # (выносим качество в конфиг, если нужно)
            success, image_bytes = cv2.imencode(".jpg", image_array, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            if not success:
                logger.error(f"Не удалось закодировать обработанный файл {original_filenames[i]}")
                continue
            
            # Добавляем файл в zip-архив
            archive_filename = f"covered_{original_filenames[i]}.jpg"
            zip_file.writestr(archive_filename, image_bytes.tobytes())

    zip_buffer.seek(0)
    return zip_buffer


@router.post(
    "/process-images/",
    summary="Обработать изображения и вернуть ZIP-архив",
    response_description="ZIP-архив с обработанными изображениями в формате JPEG.",
)
async def process_images_in_memory(
    request: Request,
    files: List[UploadFile] = File(..., description="Изображения для обработки (JPEG, PNG, WebP).")
):
    """
    Принимает список изображений, асинхронно считывает их, передает на обработку
    в фоновый поток и возвращает ZIP-архив с результатами.

    Этот эндпоинт остается отзывчивым и не блокирует сервер во время обработки.
    """
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Получен запрос на обработку {len(files)} файлов от {client_host}.")

    if not dependencies.coverer:
        raise HTTPException(status_code=503, detail="Сервис временно недоступен (модель не загружена).")

    # --- Быстрая валидация в основном потоке ---
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=413, detail=f"Слишком много файлов. Лимит: {settings.MAX_FILES_PER_REQUEST}.")

    files_data = []
    for file in files:
        if file.size > settings.MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"Файл '{file.filename}' слишком большой. Лимит: {settings.MAX_FILE_SIZE_BYTES / 1024 / 1024}MB.")
        if file.content_type not in settings.ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=415, detail=f"Неподдерживаемый тип файла: '{file.filename}'. Поддерживаются: {settings.ALLOWED_MIME_TYPES}")
        
        # Асинхронно считываем содержимое файла. Это единственная I/O операция здесь.
        contents = await file.read()
        files_data.append((file.filename, contents))
    
    if not files_data:
        raise HTTPException(status_code=400, detail="Файлы не были предоставлены.")

    # --- Запускаем ВСЮ тяжелую работу в отдельном потоке ---
    try:
        zip_buffer = await run_in_threadpool(
            _process_and_zip_sync, files_data=files_data, client_host=client_host
        )
    except Exception:
        # Ловим непредвиденные ошибки из потока
        logger.exception(f"Критическая ошибка во время фоновой обработки для {client_host}.")
        raise HTTPException(status_code=500, detail="Произошла внутренняя ошибка при обработке изображений.")

    if not zip_buffer:
        raise HTTPException(status_code=400, detail="Не было предоставлено ни одного валидного изображения для обработки.")

    logger.info(f"Обработка {len(files)} файлов для {client_host} завершена. Отправка ZIP-архива.")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=processed_images.zip"}
    )