import uuid
import os
import shutil
from pathlib import Path
from typing import Dict, List
import traceback

import cv2
from fastapi import UploadFile, BackgroundTasks
from starlette.concurrency import run_in_threadpool # <--- Необходимый импорт

from app.core.config import settings
from app.core.processor import NumberPlateCoverer

# --- Глобальные экземпляры (создаются один раз при старте) ---
# В проде это будет Redis или другая база данных
tasks_db: Dict[str, Dict] = {} 

# Инициализируем наш ML-обработчик
try:
    coverer = NumberPlateCoverer()
    SERVICE_AVAILABLE = True
except Exception as e:
    print(f"КРИТИЧЕСКАЯ ОШИБКА при инициализации ML-модели: {e}")
    coverer = None
    SERVICE_AVAILABLE = False


# --- Фоновая функция ---
def _process_images_in_background(task_id: str, input_dir: Path, output_dir: Path):
    """
    Эта функция выполняется в фоне (BackgroundTasks) и содержит основную логику обработки.
    """
    tasks_db[task_id]["status"] = "processing"
    print(f"Начата обработка задачи {task_id}...")
    
    results_list = []
    try:
        image_paths_list = list(input_dir.glob("*"))
        
        # 1. Загружаем все изображения из папки в список
        images_to_process = []
        valid_image_paths = [] # Сохраняем пути к валидным изображениям для сопоставления
        for image_path in image_paths_list:
            image = cv2.imread(str(image_path))
            if image is not None:
                images_to_process.append(image)
                valid_image_paths.append(image_path)

        # 2. Если есть что обрабатывать, вызываем пакетный метод
        if images_to_process:
            print(f"Пакетная обработка {len(images_to_process)} изображений для задачи {task_id}...")
            # Вызываем наш быстрый пакетный метод
            processed_images = coverer.cover_plates_batch(images_to_process, batch_size=8)
            print(f"Пакетная обработка для задачи {task_id} завершена.")

            # 3. Сохраняем результаты на диск
            for i, result_image in enumerate(processed_images):
                original_path = valid_image_paths[i]
                output_filename = f"covered_{original_path.name}"
                output_filepath = output_dir / output_filename
                cv2.imwrite(str(output_filepath), result_image)

                # 4. Формируем URL для скачивания и добавляем в список результатов
                results_list.append({
                    "filename": output_filename,
                    "url": f"/{settings.TASKS_STORAGE_PATH}/{task_id}/output/{output_filename}"
                })
        
        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["results"] = results_list
        print(f"Задача {task_id} успешно завершена.")
    
    except Exception as e:
        tasks_db[task_id]["status"] = "failed"
        print(f"КРИТИЧЕСКАЯ ОШИБКА при обработке задачи {task_id}: {e}")
        traceback.print_exc()
    
    finally:
        # Очищаем временные входные файлы в любом случае
        shutil.rmtree(input_dir)


# --- Вспомогательная синхронная функция для сохранения файлов ---
def _save_uploaded_files(files: List[UploadFile], destination_dir: Path):
    """
    Синхронная, блокирующая функция для сохранения файлов.
    Предназначена для вызова через run_in_threadpool.
    """
    for file in files:
        file_path = destination_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)


# --- Функции, вызываемые из API-эндпоинтов ---
async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile]) -> str:
    """
    Асинхронно создает и запускает новую задачу на обработку изображений.
    Не блокирует event loop.
    """
    task_id = str(uuid.uuid4())
    
    task_base_path = Path(settings.TASKS_STORAGE_PATH) / task_id
    task_input_dir = task_base_path / "input"
    task_output_dir = task_base_path / "output"
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    # Выполняем блокирующую операцию сохранения файлов в отдельном пуле потоков,
    # чтобы не замораживать основной событийный цикл FastAPI.
    await run_in_threadpool(_save_uploaded_files, files=files, destination_dir=task_input_dir)
            
    tasks_db[task_id] = {"status": "pending", "results": []}

    # Добавляем основную, долгую обработку в фоновые задачи FastAPI.
    # Эта функция начнет выполняться ПОСЛЕ того, как ответ будет отправлен клиенту.
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