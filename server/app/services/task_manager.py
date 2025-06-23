# server/app/services/task_manager.py

import logging
import uuid
import os
import shutil
from pathlib import Path
from typing import Dict, List
import time

import cv2
from PIL import Image, UnidentifiedImageError
import numpy as np
from fastapi import UploadFile, BackgroundTasks
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app import dependencies  # <-- ИЗМЕНЕНИЕ: Импортируем модуль с зависимостями

logger = logging.getLogger(__name__)

# --- Глобальные переменные ---
# Наша "in-memory" база данных задач. В продакшене лучше использовать Redis или другую БД.
tasks_db: Dict[str, Dict] = {}


# --- БЛОКИРУЮЩИЕ ФУНКЦИИ (для выполнения в тредпуле) ---

def _blocking_image_processing_task(task_id: str, input_dir: Path, output_dir: Path):
    """
    Эта функция ПОЛНОСТЬЮ СИНХРОННАЯ и БЛОКИРУЮЩАЯ.
    Она содержит всю тяжелую логику (чтение файлов, обработка моделью, сохранение)
    и предназначена для безопасного выполнения в отдельном потоке через run_in_threadpool.
    """
    # Устанавливаем статус "в обработке"
    tasks_db[task_id]["status"] = "processing"
    logger.info(f"[Поток: {os.getpid()}] Начата обработка задачи {task_id}...")
    
    results_list = []
    try:
        # 1. Чтение файлов (Блокирующий I/O)
        image_paths_list = list(input_dir.glob("*"))
        images_to_process = []
        valid_image_paths = []
        
        for image_path in image_paths_list:
            try:
                # Используем PIL для надежного открытия разных форматов
                with Image.open(image_path) as pil_image:
                    # Конвертируем в RGB, если нужно, и затем в BGR для OpenCV
                    image_bgr = cv2.cvtColor(np.array(pil_image.convert('RGB')), cv2.COLOR_RGB2BGR)
                    images_to_process.append(image_bgr)
                    valid_image_paths.append(image_path)
            except (UnidentifiedImageError, IOError) as e:
                logger.warning(f"Файл {image_path.name} поврежден или не является изображением. Пропускаем. Ошибка: {e}")
            except Exception:
                logger.exception(f"Неизвестная ошибка при чтении файла {image_path.name}. Пропускаем.")

        # 2. Обработка моделью (Тяжелая, блокирующая CPU/GPU операция)
        if images_to_process:
            # Получаем доступ к процессору через наш модуль зависимостей
            processed_images = dependencies.coverer.cover_plates_batch(
                images_to_process, 
                batch_size=settings.PROCESSING_BATCH_SIZE
            )
            
            # 3. Сохранение результатов (Блокирующий I/O)
            for i, result_image in enumerate(processed_images):
                original_path = valid_image_paths[i]
                output_filename = f"covered_{original_path.stem}.jpg"
                output_filepath = output_dir / output_filename
                
                # cv2.imwrite - тоже блокирующая операция
                cv2.imwrite(str(output_filepath), result_image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                
                results_list.append({
                    "filename": output_filename,
                    "url": f"/{settings.TASKS_STORAGE_PATH}/{task_id}/output/{output_filename}"
                })
        
        # Обновляем статус и результаты в нашей "базе"
        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["results"] = results_list
        logger.info(f"[Поток: {os.getpid()}] Задача {task_id} успешно завершена.")
    
    except Exception:
        tasks_db[task_id]["status"] = "failed"
        logger.exception(f"[Поток: {os.getpid()}] КРИТИЧЕСКАЯ ОШИБКА при обработке задачи {task_id}")
    
    finally:
        # Очистка временных файлов
        if input_dir.exists():
            shutil.rmtree(input_dir)
        logger.info(f"Временная директория {input_dir} для задачи {task_id} удалена.")


def _save_uploaded_files(files: List[UploadFile], destination_dir: Path):
    """Синхронная, блокирующая функция для сохранения файлов."""
    logger.info(f"Сохранение {len(files)} загруженных файлов в {destination_dir}...")
    start_time = time.time()
    for file in files:
        file_path = destination_dir / file.filename
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close() # Важно закрывать файловый дескриптор
    end_time = time.time()
    logger.info(f"Файлы сохранены за {end_time - start_time:.4f} секунд.")


# --- АСИНХРОННЫЕ ФУНКЦИИ (вызываются из API) ---

async def process_task_wrapper(task_id: str, input_dir: Path, output_dir: Path):
    """
    Асинхронная обертка, которая запускает тяжелую блокирующую функцию в тредпуле.
    Именно эту обертку мы передаем в BackgroundTasks, чтобы не блокировать event loop.
    """
    logger.info(f"Задача {task_id} передана в тредпул для фоновой обработки.")
    await run_in_threadpool(
        _blocking_image_processing_task, task_id, input_dir, output_dir
    )

async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile]) -> str:
    """
    Асинхронно создает и запускает новую задачу на обработку изображений.
    """
    task_id = str(uuid.uuid4())
    
    # Создаем директории для задачи
    task_base_path = Path(settings.TASKS_STORAGE_PATH) / task_id
    task_input_dir = task_base_path / "input"
    task_output_dir = task_base_path / "output"
    # os.makedirs - быстрая операция, можно оставить синхронной
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    # Выносим блокирующее сохранение файлов в тредпул
    await run_in_threadpool(_save_uploaded_files, files=files, destination_dir=task_input_dir)
            
    # Регистрируем задачу в нашей "базе"
    tasks_db[task_id] = {"status": "pending", "results": []}

    # ИЗМЕНЕНИЕ: Передаем в BackgroundTasks нашу АСИНХРОННУЮ обертку,
    # которая уже внутри себя вызовет блокирующую функцию в тредпуле.
    background_tasks.add_task(process_task_wrapper, task_id, task_input_dir, task_output_dir)
    
    return task_id


def get_task_status(task_id: str) -> dict:
    """Возвращает статус и результаты задачи (быстрая операция)."""
    task_data = tasks_db.get(task_id)
    if not task_data:
        return None
    
    return {
        "task_id": task_id, 
        "status": task_data["status"], 
        "results": task_data.get("results", [])
    }

def is_service_available() -> bool:
    """
    Проверяет, был ли успешно инициализирован сервис.
    Вызывается из эндпоинта перед созданием задачи.
    """
    return dependencies.coverer is not None