# test_backend.py
import shutil
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, HTTPException

# --- Настройка ---
# Папка, куда будут сохраняться все полученные файлы
RECEIVED_FILES_DIR = Path("received_files")

# Создаем FastAPI приложение
app = FastAPI(
    title="Тестовый бэкенд для приема файлов",
    description="Этот сервер принимает multipart/form-data запросы и сохраняет файлы локально.",
)

@app.on_event("startup")
def on_startup():
    """Выполняется при запуске. Создает директорию для сохранения файлов."""
    RECEIVED_FILES_DIR.mkdir(exist_ok=True)
    print(f"--- Тестовый бэкенд запущен. Файлы будут сохраняться в папку: '{RECEIVED_FILES_DIR}' ---")


@app.post("/api/images/upload")
async def handle_image_upload(
    task_id: str = Form(...),
    images: List[UploadFile] = File(...)
):
    """
    Эндпоинт, который принимает файлы от нашего сервиса обработки.
    - task_id: извлекается из поля формы 'task_id'
    - images: извлекается из поля формы 'images' (которое является массивом файлов)
    """
    print(f"\n✅ Получен запрос для Task ID: {task_id}")

    if not images:
        print("❌ Ошибка: В запросе нет файлов.")
        raise HTTPException(status_code=400, detail="No files were uploaded.")

    # Создаем подпапку для этой конкретной задачи, чтобы не было путаницы
    task_save_dir = RECEIVED_FILES_DIR / task_id
    task_save_dir.mkdir(exist_ok=True)

    print(f"  - Получено файлов: {len(images)}")
    
    saved_files = []
    for image_file in images:
        file_location = task_save_dir / image_file.filename
        try:
            # Используем shutil.copyfileobj для эффективного сохранения файла
            with open(file_location, "wb") as buffer:
                shutil.copyfileobj(image_file.file, buffer)
            
            print(f"  - Сохранен файл: {file_location}")
            saved_files.append(str(file_location))
        finally:
            # Обязательно закрываем файл, чтобы освободить ресурсы
            image_file.file.close()

    print(f"🎉 Все файлы для задачи {task_id} успешно сохранены.")

    # Возвращаем успешный JSON-ответ, похожий на тот, что мы ждем от Laravel
    return {
        "message": f"Successfully received {len(saved_files)} files for task {task_id}",
        "files_saved_at": saved_files
    }

if __name__ == "__main__":
    # Запускаем сервер на порту 8001, чтобы не конфликтовать с основным сервисом (который на 8000)
    uvicorn.run(app, host="0.0.0.0", port=8001)