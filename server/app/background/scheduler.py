# server/app/background/scheduler.py

import logging
import shutil
from pathlib import Path
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings

logger = logging.getLogger(__name__)

# Создаем единственный экземпляр планировщика, который будет импортироваться
scheduler = AsyncIOScheduler(timezone="UTC")

async def cleanup_old_tasks():
    """
    Асинхронная задача для удаления директорий задач, которые старше TTL.
    """
    logger.info("Запуск фоновой задачи очистки старых тасков...")
    tasks_dir = Path(settings.TASKS_STORAGE_PATH)
    if not tasks_dir.is_dir():
        logger.warning(f"Директория для очистки '{tasks_dir}' не найдена. Пропускаем.")
        return

    cutoff = datetime.now() - timedelta(hours=settings.TASK_STORAGE_TTL_HOURS)
    
    cleaned_count = 0
    for task_path in tasks_dir.iterdir():
        if task_path.is_dir():
            try:
                mtime = datetime.fromtimestamp(task_path.stat().st_mtime)
                if mtime < cutoff:
                    logger.info(f"Удаляем старую директорию задачи '{task_path.name}' (создана: {mtime.isoformat()})")
                    shutil.rmtree(task_path)
                    cleaned_count += 1
            except Exception as e:
                logger.exception(f"Ошибка при попытке удаления директории {task_path.name}: {e}")
    
    if cleaned_count > 0:
        logger.info(f"Задача очистки завершена. Удалено {cleaned_count} директорий.")
    else:
        logger.info("Задача очистки завершена. Старых директорий для удаления не найдено.")


def initialize_scheduler():
    """
    Инициализирует и запускает планировщик с заданными задачами.
    Вызывается при старте приложения.
    """
    # Добавляем нашу задачу очистки, которая будет запускаться каждый час
    scheduler.add_job(cleanup_old_tasks, "interval", hours=6, id="cleanup_job")
    scheduler.start()
    logger.info(f"Планировщик очистки запущен. Задачи старше {settings.TASK_STORAGE_TTL_HOURS} часов будут удаляться.")


def stop_scheduler():
    """
    Корректно останавливает планировщик.
    Вызывается при остановке приложения.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Планировщик очистки остановлен.")