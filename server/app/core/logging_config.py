# app/core/logging_config.py
import logging
from logging.config import dictConfig

# Определяем формат вывода логов
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
# Определяем формат даты
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    """
    Настраивает базовую конфигурацию логирования для вывода в консоль.
    """
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": LOG_FORMAT,
                "datefmt": DATE_FORMAT,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["console"],
        },
    }
    dictConfig(logging_config)