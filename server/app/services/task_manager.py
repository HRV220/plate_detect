# server/app/services/task_manager.py

import logging
import uuid
import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
from PIL import Image, UnidentifiedImageError
import numpy as np
from fastapi import UploadFile, BackgroundTasks
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app import dependencies

logger = logging.getLogger(__name__)

tasks_db: Dict[str, Dict] = {}


# --- Вспомогательные функции для распараллеливания ---

def _read_image(image_path: Path) -> Tuple[Path, np.ndarray]:
    """Читает одно изображение и возвращает его вместе с путем."""
    try:
        with Image.open(image_path) as pil_image:
            image_bgr = cv2.cvtColor(np.array(pil_image.convert('RGB')), cv2.COLOR_RGB2BGR)
            return image_path, image_bgr
    except (UnidentifiedImageError, IOError) as e:
        logger.warning(f"Файл {image_path.name} поврежден или не является изображением. Пропускаем. Ошибка: {e}")
    except Exception:
        logger.exception(f"Неизвестная ошибка при чтении файла {image_path.name}. Пропускаем.")
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


# --- Основная блокирующая функция (теперь оптимизированная) ---

def _blocking_image_processing_task(task_id: str, input_dir: Path, output_dir: Path):
    tasks_db[task_id]["status"] = "processing"
    logger.info(f"[Поток: {os.getpid()}] Начата обработка задачи {task_id}...")
    
    overall_start_time = time.time()
    results_list = []

    try:
        image_paths_list = list(input_dir.glob("*"))
        if not image_paths_list:
            logger.warning(f"В задаче {task_id} не найдено файлов для обработки.")
            tasks_db[task_id]["status"] = "completed"
            tasks_db[task_id]["results"] = []
            return

        # Используем ThreadPoolExecutor для параллельного чтения и сохранения
        # max_workers=None -> Python сам выберет оптимальное количество потоков
        with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
            
            # 1. ПАРАЛЛЕЛЬНОЕ ЧТЕНИЕ ФАЙЛОВ (I/O-bound)
            logger.info(f"Начато параллельное чтение {len(image_paths_list)} файлов...")
            start_read_time = time.time()
            
            # executor.map сохраняет порядок
            read_results = list(executor.map(_read_image, image_paths_list))
            
            # Отфильтровываем изображения, которые не удалось прочитать
            valid_images = [(path, img) for path, img in read_results if img is not None]
            if not valid_images:
                raise ValueError("Не удалось прочитать ни одного корректного изображения.")

            valid_image_paths = [item[0] for item in valid_images]
            images_to_process = [item[1] for item in valid_images]
            
            logger.info(f"Чтение завершено за {time.time() - start_read_time:.4f} сек.")

            # 2. ПАКЕТНАЯ ОБРАБОТКА МОДЕЛЬЮ (CPU/GPU-bound)
            # Эта часть остается без изменений, т.к. модель уже оптимизирована для батчинга
            processed_images = dependencies.coverer.cover_plates_batch(
                images_to_process, 
                batch_size=settings.PROCESSING_BATCH_SIZE
            )

            # 3. ПАРАЛЛЕЛЬНОЕ СОХРАНЕНИЕ РЕЗУЛЬТАТОВ (I/O + CPU-bound)
            logger.info(f"Начато параллельное сохранение {len(processed_images)} результатов...")
            start_save_time = time.time()

            # Готовим аргументы для функции сохранения
            save_args = [
                (img, path, output_dir, task_id, settings.TASKS_STORAGE_PATH) 
                for img, path in zip(processed_images, valid_image_paths)
            ]
            
            results_list = list(executor.map(_save_image_webp, save_args))

            logger.info(f"Сохранение завершено за {time.time() - start_save_time:.4f} сек.")

        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["results"] = results_list
        total_time = time.time() - overall_start_time
        logger.info(f"[Поток: {os.getpid()}] Задача {task_id} успешно завершена за {total_time:.4f} сек.")
    
    except Exception:
        tasks_db[task_id]["status"] = "failed"
        logger.exception(f"[Поток: {os.getpid()}] КРИТИЧЕСКАЯ ОШИБКА при обработке задачи {task_id}")
    
    finally:
        if input_dir.exists():
            shutil.rmtree(input_dir)
        logger.info(f"Временная директория {input_dir} для задачи {task_id} удалена.")


# --- Остальная часть файла остается без изменений ---

def _save_uploaded_files(files: List[UploadFile], destination_dir: Path):
    """Синхронная, блокирующая функция для сохранения файлов."""
    logger.info(f"Сохранение {len(files)} загруженных файлов в {destination_dir}...")
    start_time = time.time()
    # Эту часть тоже можно распараллелить, но обычно она не является узким местом,
    # так как FastAPI уже эффективно стримит данные на диск.
    for file in files:
        # ВАЖНО: добавить санитизацию имени файла, если еще не сделали
        safe_filename = file.filename.replace("..", "") # Простейшая санитизация
        file_path = destination_dir / safe_filename
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
    end_time = time.time()
    logger.info(f"Файлы сохранены за {end_time - start_time:.4f} секунд.")

async def process_task_wrapper(task_id: str, input_dir: Path, output_dir: Path):
    logger.info(f"Задача {task_id} передана в тредпул для фоновой обработки.")
    await run_in_threadpool(
        _blocking_image_processing_task, task_id, input_dir, output_dir
    )

async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile]) -> str:
    task_id = str(uuid.uuid4())
    
    task_base_path = Path(settings.TASKS_STORAGE_PATH) / task_id
    task_input_dir = task_base_path / "input"
    task_output_dir = task_base_path / "output"
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    await run_in_threadpool(_save_uploaded_files, files=files, destination_dir=task_input_dir)
            
    tasks_db[task_id] = {"status": "pending", "results": []}

    background_tasks.add_task(process_task_wrapper, task_id, task_input_dir, task_output_dir)
    
    return task_id

def get_task_status(task_id: str) -> dict:
    task_data = tasks_db.get(task_id)
    if not task_data:
        return None
    
    return {
        "task_id": task_id, 
        "status": task_data["status"], 
        "results": task_data.get("results", [])
    }

def is_service_available() -> bool:
    return dependencies.coverer is not None