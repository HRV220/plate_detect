# server/app/services/callback_sender.py
import logging
from typing import Dict, Any, List
from pathlib import Path

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_result_to_backend_sync(task_data: Dict[str, Any]):
    """
    СИНХРОННАЯ функция для отправки JSON-уведомления на бэкенд.
    Эта функция предназначена для вызова через run_in_threadpool.
    """
    if not settings.BACKEND_CALLBACK_URL:
        # URL для JSON-уведомлений не задан, ничего не делаем.
        return

    task_id = task_data.get("task_id")
    logger.info(f"Отправка JSON-уведомления для задачи {task_id} на {settings.BACKEND_CALLBACK_URL}")

    try:
        response = requests.post(
            url=settings.BACKEND_CALLBACK_URL,
            json=task_data,
            timeout=30
        )
        response.raise_for_status()
        logger.info(f"JSON-уведомление для задачи {task_id} успешно отправлено.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при отправке JSON-уведомления для задачи {task_id}: {e}")
    except Exception:
        logger.exception(f"Непредвиденная ошибка при отправке JSON-уведомления для задачи {task_id}.")


# --- НОВАЯ ФУНКЦИЯ, ДОБАВЛЕННАЯ НА ЭТОМ ШАГЕ ---

def upload_processed_images_sync(task_id: str, output_dir: Path, results: List[Dict[str, str]]):
    """
    СИНХРОННАЯ функция для загрузки обработанных файлов на бэкенд.
    Использует multipart/form-data.
    Предназначена для вызова через run_in_threadpool.
    """
    # 1. Проверяем, задан ли URL. Если нет - ничего не делаем.
    if not settings.BACKEND_UPLOAD_URL:
        logger.info("BACKEND_UPLOAD_URL не настроен. Пропускаем загрузку файлов.")
        return

    logger.info(f"Начинаем загрузку {len(results)} файлов для задачи {task_id} на {settings.BACKEND_UPLOAD_URL}")

    # 2. Подготавливаем данные для запроса
    # Мы отправим task_id в теле запроса как обычное поле формы.
    form_data = {'task_id': task_id}
    
    files_to_upload_tuples = []
    opened_files = [] # Список для хранения открытых файловых объектов, чтобы гарантированно их закрыть

    try:
        # 3. Подготавливаем файлы для отправки
        for result_file in results:
            filename = result_file['filename']
            file_path = output_dir / filename
            
            if not file_path.exists():
                logger.warning(f"Файл {file_path} не найден для загрузки. Пропускаем.")
                continue

            # Открываем файл в бинарном режиме и добавляем в список для закрытия
            file_object = open(file_path, 'rb')
            opened_files.append(file_object)

            # requests ожидает список кортежей: (имя_поля, (имя_файла, объект_файла, тип_контента))
            # 'images' - имя поля, которое Laravel будет искать в запросе.
            files_to_upload_tuples.append(('images', (filename, file_object, 'image/webp')))
        
        if not files_to_upload_tuples:
            logger.warning(f"Для задачи {task_id} нет файлов для загрузки.")
            return

        # 4. Отправляем запрос
        response = requests.post(
            url=settings.BACKEND_UPLOAD_URL,
            data=form_data,             # Поля формы (task_id)
            files=files_to_upload_tuples, # Файлы
            timeout=120                 # Увеличим таймаут, т.к. загрузка файлов может быть долгой
        )
        response.raise_for_status() # Вызовет ошибку для статусов 4xx/5xx
        logger.info(f"Файлы для задачи {task_id} успешно загружены. Статус ответа: {response.status_code}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Сетевая ошибка при загрузке файлов для задачи {task_id}: {e}")
    except Exception:
        logger.exception(f"Непредвиденная ошибка при подготовке или загрузке файлов для задачи {task_id}.")
    finally:
        # 5. ВАЖНО: Закрываем все открытые файлы, чтобы избежать утечек ресурсов
        for file_obj in opened_files:
            file_obj.close()