# main.py (версия с фоновой обработкой и URL)
import cv2
import numpy as np
import uuid
import os
import shutil
from typing import List, Dict
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Path as FastAPIPath
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.processor import NumberPlateCoverer

# --- Конфигурация ---
MODEL_PATH = "models/best.pt"
COVER_IMAGE_PATH = "static/cover.png"
DEVICE = "cuda"

# --- Хранилище задач и файлов ---
TASKS_STORAGE_PATH = Path("tasks_storage")
os.makedirs(TASKS_STORAGE_PATH, exist_ok=True)
# Глобальный словарь для отслеживания статуса задач. В проде лучше использовать Redis.
tasks_db: Dict[str, Dict] = {}

# --- Модели данных Pydantic ---
class TaskResponse(BaseModel):
    task_id: str = Field(..., description="Уникальный идентификатор задачи.")

class ResultFile(BaseModel):
    filename: str
    url: str

class TaskStatusResponse(BaseModel):
    task_id: str
    status: str = Field(..., description="Статус задачи: pending, processing, completed, failed.")
    results: List[ResultFile] = Field([], description="Список файлов с результатами (появляется после завершения).")

# --- Инициализация FastAPI ---
app = FastAPI(title="Асинхронный сервис обработки номеров")

# Монтируем директорию с результатами как статическую
# Теперь файлы из tasks_storage/ можно будет скачать по URL /results/
app.mount("/results", StaticFiles(directory=TASKS_STORAGE_PATH), name="results")

# Инициализация модели
try:
    coverer = NumberPlateCoverer(model_path=MODEL_PATH, cover_image_path=COVER_IMAGE_PATH, device=DEVICE)
except FileNotFoundError as e:
    print(f"Критическая ошибка: {e}")
    coverer = None

# --- Функция фоновой обработки ---
def process_images_in_background(task_id: str, input_dir: Path, output_dir: Path):
    """Эта функция будет выполняться в фоне."""
    tasks_db[task_id]["status"] = "processing"
    print(f"Начата обработка задачи {task_id}...")
    
    results_list = []
    try:
        for image_path in input_dir.glob("*"):
            image = cv2.imread(str(image_path))
            if image is None: continue

            result_image = coverer.cover_plate(image)
            
            output_filename = f"covered_{image_path.name}"
            output_filepath = output_dir / output_filename
            cv2.imwrite(str(output_filepath), result_image)

            results_list.append(ResultFile(
                filename=output_filename,
                url=f"/results/{task_id}/output/{output_filename}" # URL для скачивания
            ).dict())
        
        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["results"] = results_list
        print(f"Задача {task_id} успешно завершена.")
    
    except Exception as e:
        tasks_db[task_id]["status"] = "failed"
        print(f"Ошибка при обработке задачи {task_id}: {e}")
    
    finally:
        # Очищаем временные входные файлы
        shutil.rmtree(input_dir)


# --- Эндпоинты API ---
@app.post("/process-task/", response_model=TaskResponse, status_code=202)
async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    if coverer is None:
        raise HTTPException(status_code=503, detail="Сервис недоступен.")

    task_id = str(uuid.uuid4())
    
    # Создаем уникальные папки для задачи
    task_input_dir = TASKS_STORAGE_PATH / task_id / "input"
    task_output_dir = TASKS_STORAGE_PATH / task_id / "output"
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    # Сохраняем загруженные файлы на диск
    for file in files:
        file_path = task_input_dir / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    # Регистрируем задачу
    tasks_db[task_id] = {"status": "pending", "results": []}

    # Добавляем задачу в фон
    background_tasks.add_task(process_images_in_background, task_id, task_input_dir, task_output_dir)

    return TaskResponse(task_id=task_id)


@app.get("/task-status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str = FastAPIPath(..., description="ID задачи, полученный от /process-task/.")):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача с таким ID не найдена.")
    
    return TaskStatusResponse(task_id=task_id, status=task["status"], results=task.get("results", []))