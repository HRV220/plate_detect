# main.py
import cv2
import numpy as np
import uuid
import os
import shutil
import torch
from typing import List, Dict
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Path as FastAPIPath
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Предполагаем, что processor.py находится в папке src
from src.processor import NumberPlateCoverer

# --- Конфигурация ---
MODEL_PATH = "models/best.pt"
COVER_IMAGE_PATH = "static/cover.png"

# Определяем устройство: используем CUDA, если доступно, иначе CPU.
# Можно переопределить переменной окружения, например: PROCESSING_DEVICE=cpu
DEFAULT_DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
DEVICE = os.getenv("PROCESSING_DEVICE", DEFAULT_DEVICE)

# Размер батча для обработки. Можно вынести в переменные окружения.
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "8"))

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
app = FastAPI(
    title="Асинхронный сервис обработки номеров",
    description="Сервис для наложения заглушек на автомобильные номера с использованием YOLOv8-OBB и пакетной обработки.",
    version="2.0.0"
)

# Монтируем директорию с результатами как статическую
app.mount("/results", StaticFiles(directory=TASKS_STORAGE_PATH), name="results")

# Инициализация модели
try:
    print(f"Инициализация модели на устройстве: {DEVICE}")
    coverer = NumberPlateCoverer(model_path=MODEL_PATH, cover_image_path=COVER_IMAGE_PATH, device=DEVICE)
except Exception as e:
    print(f"Критическая ошибка при инициализации модели: {e}")
    coverer = None

# --- Функция фоновой обработки (с пакетной обработкой) ---
def process_images_in_background(task_id: str, input_dir: Path, output_dir: Path):
    """
    Эта функция выполняется в фоне и использует пакетную обработку.
    """
    tasks_db[task_id]["status"] = "processing"
    print(f"Начата обработка задачи {task_id}...")
    
    results_list = []
    try:
        image_paths_list = list(input_dir.glob("*"))
        
        # 1. Загружаем все изображения в список
        images_to_process = []
        valid_image_paths = []
        for image_path in image_paths_list:
            # Проверяем расширения, чтобы не пытаться читать не-изображения
            if image_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                image = cv2.imread(str(image_path))
                if image is not None:
                    images_to_process.append(image)
                    valid_image_paths.append(image_path)
                else:
                    print(f"Предупреждение: не удалось прочитать файл {image_path.name}")
        
        # 2. Если есть что обрабатывать, вызываем пакетный метод
        if images_to_process:
            print(f"Начинаю пакетную обработку {len(images_to_process)} изображений (batch_size={BATCH_SIZE})...")
            processed_images = coverer.cover_plates_batch(images_to_process, batch_size=BATCH_SIZE)
            print(f"Пакетная обработка для задачи {task_id} завершена.")

            # 3. Сохраняем результаты
            for i, result_image in enumerate(processed_images):
                original_path = valid_image_paths[i]
                output_filename = f"covered_{original_path.name}"
                output_filepath = output_dir / output_filename
                cv2.imwrite(str(output_filepath), result_image)

                results_list.append(ResultFile(
                    filename=output_filename,
                    url=f"/results/{task_id}/output/{output_filename}"
                ).dict())
        else:
            print(f"В задаче {task_id} не найдено подходящих изображений для обработки.")

        tasks_db[task_id]["status"] = "completed"
        tasks_db[task_id]["results"] = results_list
        print(f"Задача {task_id} успешно завершена.")
    
    except Exception as e:
        tasks_db[task_id]["status"] = "failed"
        # Логируем ошибку для дальнейшего анализа
        print(f"Критическая ошибка при обработке задачи {task_id}: {e}")
    
    finally:
        # Очищаем временные входные файлы
        try:
            shutil.rmtree(input_dir)
            print(f"Временная папка {input_dir} для задачи {task_id} удалена.")
        except OSError as e:
            print(f"Ошибка при удалении временной папки {input_dir}: {e}")


# --- Эндпоинты API ---
@app.on_event("startup")
async def startup_event():
    if coverer is None:
        print("ВНИМАНИЕ: Сервис запускается в нерабочем состоянии, модель не была загружена.")

@app.get("/", summary="Проверка статуса сервиса")
def read_root():
    if coverer is None:
        return {"status": "error", "message": "Сервис не смог инициализировать модель."}
    return {"status": "ok", "message": f"Сервис запущен и работает на устройстве: {DEVICE}."}
    
@app.post("/process-task/", response_model=TaskResponse, status_code=202)
async def create_processing_task(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    if coverer is None:
        raise HTTPException(status_code=503, detail="Сервис временно недоступен из-за ошибки инициализации модели.")

    task_id = str(uuid.uuid4())
    
    task_input_dir = TASKS_STORAGE_PATH / task_id / "input"
    task_output_dir = TASKS_STORAGE_PATH / task_id / "output"
    os.makedirs(task_input_dir, exist_ok=True)
    os.makedirs(task_output_dir, exist_ok=True)

    # Сохраняем загруженные файлы на диск
    for file in files:
        if file.filename:
            file_path = task_input_dir / Path(file.filename).name
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
    tasks_db[task_id] = {"status": "pending", "results": []}
    background_tasks.add_task(process_images_in_background, task_id, task_input_dir, task_output_dir)

    return TaskResponse(task_id=task_id)


@app.get("/task-status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str = FastAPIPath(..., description="ID задачи, полученный от /process-task/.")):
    task = tasks_db.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Задача с таким ID не найдена.")
    
    return TaskStatusResponse(task_id=task_id, status=task["status"], results=task.get("results", []))