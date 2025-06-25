# server/app/background/cleaner.py
import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta

from app.core.config import settings

logger = logging.getLogger(__name__)

def cleanup_old_tasks():
    """
    Сканирует директорию хранения задач и удаляет папки, которые были
    изменены более чем `TASK_STORAGE_TTL_HOURS` часов назад.
    """
    storage_path = Path(settings.TASKS_STORAGE_PATH)
    if not storage_path.is_dir():
        return

    logger.info("--- [Планировщик] Запуск задачи очистки старых директорий ---")
    
    # Устанавливаем порог времени для удаления
    ttl_hours = settings.TASK_STORAGE_TTL_HOURS
    time_threshold = datetime.now() - timedelta(hours=ttl_hours)
    
    deleted_count = 0
    for task_dir in storage_path.iterdir():
        # Проверяем, что это директория, а не случайный файл
        if not task_dir.is_dir():
            continue
        
        try:
            # Получаем время последнего изменения директории
            modified_time_ts = task_dir.stat().st_mtime
            modified_time = datetime.fromtimestamp(modified_time_ts)

            if modified_time < time_threshold:
                logger.info(f"Удаление старой директории: {task_dir} (последнее изменение: {modified_time})")
                shutil.rmtree(task_dir)
                deleted_count += 1
        except FileNotFoundError:
            # Директория могла быть удалена другим процессом между шагами, это нормально
            continue
        except Exception:
            logger.exception(f"Не удалось удалить директорию {task_dir}")
            
    if deleted_count > 0:
        logger.info(f"--- [Планировщик] Очистка завершена. Удалено директорий: {deleted_count} ---")
    else:
        logger.info("--- [Планировщик] Очистка завершена. Старых директорий для удаления не найдено. ---")