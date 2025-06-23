import logging
import uuid
import os
import shutil
from pathlib import Path
from typing import Dict, List
import traceback
import time

import cv2
from PIL import Image, UnidentifiedImageError
import numpy as np
from fastapi import UploadFile, BackgroundTasks
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.processor import NumberPlateCoverer

# Создаем логгер для этого модуля
logger = logging.getLogger(__name__)

# --- Глобальные экземпляры (создаются один раз при старте) ---
tasks_db: Dict[str, Dict] = {} 

try:
    coverer = NumberPlateCoverer()
    SERVICE_AVAILABLE = True
except Exception as e:
    logger.exception(f"КРИТИЧЕСКАЯ ОШИБКА при инициализации ML-модели: {e}")
    coverer = None
    SERVICE_AVAILABLE = False


# --- Фоновая функция ---
def _process_images_in_background(task_id: str, input_dir: Path, output_dir: Path):
    """
    Эта функция выполняется в фоне (BackgroundTasks) и содержит основную логику обработки.
    """
    tasks_db[task_id]["status"] = "processing"
    logger.info(f"Начата обработка задачи {task_id}...")
    
    results_list = []
    try:
        image_paths_list = list(input_dir.glob("*"))
        images_to_process = []
        valid_image_paths = []
        
        logger.info(f"Чтение {len(image_paths_list)} файлов для задачи {task_id}...")
        for image_path in image_paths_list:
            try:
                pil_image = Image.open(image_path)
                if pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                
                image_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                images_to_process.append(image_bgr)
                valid_image_paths.append(image_path)

            except UnidentifiedImageError:
                logger.warning(f"Файл {image_path.name} не является изображением. Пропускаем.")
            except Exception:
                logger.exception(f"Неизвестная ошибка при чтении файла {image_path.name}. Пропускаем.")

        if images_to_process:
            processed_images = coverer.cover_plates_batch(images_to_process, batch_size=8)
            
            logger.info(f"Сохранение {len(processed_images)} обработанных файлов для задачи {task_id}...")
            for i, result_image in enumerate(processed_images):
                original_path = valid_image_paths[i]
                base_name = original_path.stem
                output_filename = f"covered_{base_name}.jpg"
                output_filepath = output_dir / output_filename
                
                cv2.imwrite(str(output_filepath), result_image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                
                results_list.append({
                    "filename": output_filename,
                    "url": f"/{settings.TASKS_STORAGE_PATH}/{task_id}/output/{output_filename}"
                })
        
        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["results"] = results_list
        logger.info(f"Задача {task_id} успешно завершена.")
    
    except Exception:
        tasks_db[task_id]["status"] = "failed"
        logger.exception(f"КРИТИЧЕСКАЯ ОШИБКА в фоновой обработке задачи {task_id}")
    
    finally:
        if input_dir.exists():
            shutil.rmtree(input_dir)


# --- Вспомогательная синхронная функция для сохранения файлов ---
def _save_uploaded_files(files: List[UploadFile], destination_dir: Path):
    """
    Синхронная, блокирующая функция для сохранения файлов.
    """
    logger.info(f"Сохранение {len(files)} загруженных файлов в {destination_dir}...")
    start_time = time.time() # Добавим замер времени
    for file in files:
        file_path = destination_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    end_time = time.time()
    logger.info(f"Файлы сохранены за {end_time - start_time:.4f} секунд.")


# --- Функции, вызываемые из API-эндпоинтов ---
async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile]) -> str:
    """
    Асинхронно создает и запускает новую задачу на обработку изображений.
    """
    task_id = str(uuid.uuid4())
    
    task_base_path = Path(settings.TASKS_STORAGE_PATH) / task_id
    task_input_dir = task_base_path / "input"
    task_output_dir = task_base_path / "output"
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    await run_in_threadpool(_save_uploaded_files, files=files, destination_dir=task_input_dir)
            
    tasks_db[task_id] = {"status": "pending", "results": []}

    background_tasks.add_task(_process_images_in_background, task_id, task_input_dir, task_output_dir)
    
    return task_id


def get_task_status(task_id: str) -> dict:
    """
    Возвращает статус и результаты задачи из нашего "in-memory" хранилища.
    """
    task = tasks_db.get(task_id)
    if not task:
        return None
    
    return {
        "task_id": task_id, 
        "status": task["status"], 
        "results": task.get("results", [])
    }