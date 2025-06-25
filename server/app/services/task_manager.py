# server/app/services/task_manager.py

import logging
import uuid
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import time
from concurrent.futures import ThreadPoolExecutor
import json

import cv2
from PIL import Image, UnidentifiedImageError
import numpy as np
from fastapi import UploadFile, BackgroundTasks
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app import dependencies

from app.services.callback_sender import send_result_to_backend_sync, upload_processed_images_sync

logger = logging.getLogger(__name__)


def _read_image(image_path: Path) -> Tuple[Path, np.ndarray]:
    """Читает одно изображение и возвращает его вместе с путем."""
    try:
        with Image.open(image_path) as pil_image:
            image_bgr = cv2.cvtColor(np.array(pil_image.convert('RGB')), cv2.COLOR_RGB2BGR)
            return image_path, image_bgr
    except (UnidentifiedImageError, IOError) as e:
        logger.warning(f"Файл {image_path.name} поврежден. Пропускаем. Ошибка: {e}")
    except Exception:
        logger.exception(f"Неизвестная ошибка при чтении файла {image_path.name}.")
    return image_path, None


def _save_image_webp(args: Tuple[np.ndarray, Path, Path, str, str]) -> Dict:
    """Сохраняет одно изображение в WebP и возвращает информацию о результате."""
    result_image, original_path, output_dir, task_id, storage_path_prefix = args
    output_filename = f"covered_{original_path.stem}.webp"
    output_filepath = output_dir / output_filename
    result_image_rgb = cv2.cvtColor(result_image, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(result_image_rgb)
    pil_img.save(str(output_filepath), 'webp', quality=90)
    return {
        "filename": output_filename,
        "url": f"/{storage_path_prefix}/{task_id}/output/{output_filename}"
    }


def _save_uploaded_files(files: List[UploadFile], destination_dir: Path):
    """Синхронная, блокирующая функция для сохранения файлов."""
    logger.info(f"Сохранение {len(files)} файлов в {destination_dir}...")
    start_time = time.time()
    for file in files:
        safe_filename = Path(file.filename).name.replace("..", "")
        file_path = destination_dir / safe_filename
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
    end_time = time.time()
    logger.info(f"Файлы сохранены за {end_time - start_time:.4f} секунд.")


async def process_task_wrapper(task_id: str, input_dir: Path, output_dir: Path):
    """
    Асинхронная обертка для фоновой задачи.
    Координирует вычисления, обновляет статусы и отправляет коллбэки/файлы.
    """
    task_key = f"task:{task_id}"
    logger.info(f"Задача {task_id} передана на обработку.")

    try:
        await dependencies.redis_client.hset(task_key, "status", "processing")
        logger.info(f"Статус задачи {task_id} изменен на 'processing'.")

        overall_start_time = time.time()
        
        def _blocking_operations():
            image_paths_list = list(input_dir.glob("*"))
            if not image_paths_list:
                logger.warning(f"В задаче {task_id} не найдено файлов для обработки.")
                return []

            with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
                read_results = list(executor.map(_read_image, image_paths_list))
                valid_images = [(path, img) for path, img in read_results if img is not None]
                if not valid_images:
                    raise ValueError("Не удалось прочитать ни одного корректного изображения.")

                valid_image_paths = [item[0] for item in valid_images]
                images_to_process = [item[1] for item in valid_images]

                processed_images = dependencies.coverer.cover_plates_batch(
                    images_to_process, batch_size=settings.PROCESSING_BATCH_SIZE
                )
                
                save_args = [
                    (img, path, output_dir, task_id, settings.TASKS_STORAGE_PATH)
                    for img, path in zip(processed_images, valid_image_paths)
                ]
                results_list = list(executor.map(_save_image_webp, save_args))
                return results_list
        
        final_results = await run_in_threadpool(_blocking_operations)

        task_data = {
            "task_id": task_id,
            "status": "completed",
            "results": final_results
        }

        await dependencies.redis_client.hset(task_key, mapping={
            "status": task_data["status"],
            "results": json.dumps(task_data["results"])
        })
        
        total_time = time.time() - overall_start_time
        logger.info(f"Задача {task_id} успешно завершена за {total_time:.4f} сек.")

        await run_in_threadpool(send_result_to_backend_sync, task_data=task_data)
        
        await run_in_threadpool(
            upload_processed_images_sync, 
            task_id=task_id, 
            output_dir=output_dir, 
            results=final_results
        )

    except Exception:
        await dependencies.redis_client.hset(task_key, "status", "failed")
        logger.exception(f"КРИТИЧЕСКАЯ ОШИБКА при обработке задачи {task_id}")
    
    finally:
        if input_dir.exists():
            await run_in_threadpool(shutil.rmtree, input_dir)
            logger.info(f"Временная директория {input_dir} для задачи {task_id} удалена.")


async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile]) -> str:
    task_id = str(uuid.uuid4())
    task_key = f"task:{task_id}"
    
    task_base_path = Path(settings.TASKS_STORAGE_PATH) / task_id
    task_input_dir = task_base_path / "input"
    task_output_dir = task_base_path / "output"
    
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    await run_in_threadpool(_save_uploaded_files, files=files, destination_dir=task_input_dir)
            
    await dependencies.redis_client.hset(
        task_key, 
        mapping={ "status": "pending", "results": json.dumps([]) }
    )
    await dependencies.redis_client.expire(task_key, settings.TASK_STORAGE_TTL_HOURS * 3600)
    
    background_tasks.add_task(process_task_wrapper, task_id, task_input_dir, task_output_dir)
    
    return task_id


async def get_task_status(task_id: str) -> dict:
    task_key = f"task:{task_id}"
    task_data = await dependencies.redis_client.hgetall(task_key)
    
    if not task_data:
        return None
    
    results = json.loads(task_data.get("results", "[]"))
    
    return {
        "task_id": task_id, 
        "status": task_data["status"], 
        "results": results
    }


def is_service_available() -> bool:
    return dependencies.coverer is not None and dependencies.redis_client is not None