# Этап 1: Базовый образ
# Используем официальный образ Python 3.10-slim. Он содержит минимально
# необходимый набор компонентов, что делает финальный образ меньше.
FROM python:3.10-slim

# Этап 2: Установка системных переменных
# Устанавливаем рабочую директорию внутри контейнера.
# Все последующие команды будут выполняться относительно этой папки.
WORKDIR /app

# Настраиваем переменные окружения для Python:
# - PYTHONDONTWRITEBYTECODE=1: Отключает создание .pyc файлов.
# - PYTHONUNBUFFERED=1: Гарантирует, что вывод print/logging сразу попадает
#   в логи контейнера, а не буферизируется.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Этап 3: Установка системных зависимостей
# Устанавливаем библиотеки, необходимые для работы OpenCV и Pillow с WebP.
# --no-install-recommends - не устанавливать необязательные пакеты.
# apt-get clean && rm -rf /var/lib/apt/lists/* - очистка кэша для уменьшения размера образа.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libwebp-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Этап 4: Установка Python-зависимостей
# Копируем только requirements.txt. Этот слой будет кэширован, если файл
# не изменится, что значительно ускорит последующие сборки.
COPY requirements.txt .

# Устанавливаем PyTorch для CPU. Вынесено в отдельную команду для надежности
# и лучшего кэширования.
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Устанавливаем все остальные зависимости из requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Этап 5: Копирование кода приложения
# Копируем папки с кодом и ресурсами в рабочую директорию /app контейнера.
# Используется .dockerignore для исключения ненужных файлов.
COPY ./app ./app
COPY ./models ./models
COPY ./static ./static

# Этап 6: Запуск приложения
# Сообщаем Docker, что наше приложение слушает порт 8000
EXPOSE 8000

# Устанавливаем переменную окружения для устройства по умолчанию.
# Можно будет переопределить при запуске: docker run -e PROCESSING_DEVICE=cuda ...
ENV PROCESSING_DEVICE=cpu

# Команда для запуска нашего FastAPI приложения через Gunicorn в продакшен-режиме.
# -w 4: 4 рабочих процесса. Хорошее начало, можно настроить (например, 2 * кол-во ядер + 1).
# -k uvicorn.workers.UvicornWorker: Использовать uvicorn для обработки асинхронных запросов.
# -b 0.0.0.0:8000: Слушать на всех сетевых интерфейсах на порту 8000.
# app.main:app: Путь к экземпляру FastAPI (<модуль>:<переменная>).
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app.main:app"]