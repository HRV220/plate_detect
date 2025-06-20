# test_script.py (версия для асинхронного API)
import requests
import os
import glob
import time

# --- Конфигурация ---
BASE_URL = "http://127.0.0.1:8000"
PROCESS_URL = f"{BASE_URL}/process-task/"
STATUS_URL = f"{BASE_URL}/task-status/"
TEST_IMAGES_DIR = "test_images/"
OUTPUT_DIR = "output/async_results/"

# --- Основной код ---
def main():
    # 1. Находим и отправляем файлы
    image_paths = glob.glob(os.path.join(TEST_IMAGES_DIR, "*.jpg")) + \
                  glob.glob(os.path.join(TEST_IMAGES_DIR, "*.png"))
    if not image_paths:
        print(f"Не найдены изображения для теста в {TEST_IMAGES_DIR}")
        return

    files_to_send = [('files', (os.path.basename(p), open(p, 'rb'))) for p in image_paths]
    
    try:
        print(f"Отправка {len(image_paths)} файлов для создания задачи...")
        response = requests.post(PROCESS_URL, files=files_to_send)
        response.raise_for_status() # Проверка на HTTP ошибки
        task_id = response.json()["task_id"]
        print(f"Задача успешно создана. Task ID: {task_id}")

    except requests.RequestException as e:
        print(f"Ошибка при создании задачи: {e}")
        return
    finally:
        for _, file_tuple in files_to_send:
            file_tuple[1].close()

    # 2. Опрашиваем статус задачи
    print("Начинаем опрос статуса задачи...")
    while True:
        try:
            status_response = requests.get(f"{STATUS_URL}{task_id}")
            status_response.raise_for_status()
            data = status_response.json()
            status = data["status"]
            print(f"  Текущий статус: {status}")

            if status == "completed":
                print("Обработка завершена!")
                results = data.get("results", [])
                break
            elif status == "failed":
                print("Ошибка обработки задачи на сервере.")
                return
            
            time.sleep(2) # Пауза перед следующим запросом

        except requests.RequestException as e:
            print(f"Ошибка при опросе статуса: {e}")
            return
            
    # 3. Скачиваем файлы по полученным URL
    if not results:
        print("Задача завершена, но не вернула результатов.")
        return
        
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Скачивание {len(results)} файлов в {OUTPUT_DIR}...")
    
    for result in results:
        file_url = f"{BASE_URL}{result['url']}"
        filename = result['filename']
        try:
            print(f"  Скачивание {filename} из {file_url}")
            file_response = requests.get(file_url, stream=True)
            file_response.raise_for_status()
            
            with open(os.path.join(OUTPUT_DIR, filename), 'wb') as f:
                for chunk in file_response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except requests.RequestException as e:
            print(f"Ошибка при скачивании файла {filename}: {e}")

    print("Все файлы успешно скачаны.")

if __name__ == "__main__":
    main()