Сервис для анонимизации номерных знаков v1.0

![alt text](https://img.shields.io/badge/Python-3.10-blue.svg)

![alt text](https://img.shields.io/badge/FastAPI-0.115-green.svg)

![alt text](https://img.shields.io/badge/Docker-Ready-blue.svg)

![alt text](https://img.shields.io/badge/License-MIT-lightgrey.svg)

Продакшен-готовый асинхронный сервис на FastAPI для детекции автомобильных номеров на изображениях и наложения на них кастомной заглушки.

# Ключевые возможности

- Асинхронная обработка: Сервис мгновенно принимает задачи и обрабатывает их в фоновом режиме, не заставляя клиента ждать.

- Пакетная обработка: Эффективная обработка до 50 изображений за один запрос для максимальной производительности.

- Высокая производительность: Использует оптимизированную модель YOLOv8-OBB для точной детекции номеров и ThreadPoolExecutor для распараллеливания I/O операций.

- Поддержка форматов: Принимает изображения JPEG, PNG, WebP и отдает результаты в экономичном формате WebP.

- Надежность: Профессиональная архитектура, централизованная конфигурация, полное логирование и обработка ошибок.

- Готовность к развертыванию: Упакован в Docker-контейнер с непривилегированным пользователем для легкого и безопасного деплоя.

- Автоматическая документация: Интерактивная документация API доступна через Swagger UI (/docs) и ReDoc (/redoc).

# Технологический стек

- Фреймворк: FastAPI

- Сервер: Gunicorn + Uvicorn

- ML-модель: YOLOv8-OBB (Ultralytics)

- Обработка изображений: OpenCV, Pillow

- Валидация данных: Pydantic

- Контейнеризация: Docker

- Фоновые задачи: APScheduler

# Структура проекта

```
plate_detect/
├── server/
│ ├── app/ # Основной код приложения
│ │ ├── api/ # Эндпоинты, схемы и роутеры API
│ │ ├── background/ # Модули для фоновых задач (очистка)
│ │ ├── core/ # Ядро приложения (конфиг, ML-процессор)
│ │ ├── services/ # Бизнес-логика (менеджер задач)
│ │ ├── dependencies.py # Управление зависимостями
│ │ └── main.py # Точка входа в приложение
│ ├── models/ # Директория для ML-моделей (\*.pt)
│ ├── static/ # Статические файлы (изображение-заглушка)
│ ├── tasks_storage/ # Хранилище для обработанных задач (создается автоматически)
│ ├── .dockerignore # Файлы, игнорируемые Docker
│ ├── Dockerfile # Инструкция по сборке Docker-образа
│ ├── requirements.in # Исходный список зависимостей
│ └── requirements.txt # "Замороженный" список для продакшена
└── README.md
```

# Установка и запуск через Docker

Проект упакован в Docker, что делает его запуск быстрым и воспроизводимым на любой системе.

# Пререквизиты

- Git

- Docker

# Пошаговая инструкция

1. Клонируйте репозиторий:

```bash
git clone https://github.com/HRV220/plate_detect.git
cd plate_detect/server/
```

2. Подготовьте необходимые ресурсы:

- Поместите вашу обученную модель (best.pt) в папку server/models/.

- Поместите ваше изображение-заглушку (cover.png) в папку server/static/.

3. Соберите Docker-образ:
   Эта команда прочитает Dockerfile и соберет самодостаточный образ приложения.

```bash
docker build -t plate-cover-service .
```

4. Запустите Docker-контейнер:
   Эта команда запустит ваш сервис в фоновом режиме. Выберите команду, соответствующую вашей ОС.

Для Linux, macOS и Windows (PowerShell):

```bash
docker run -d -p 8000:8000 `  --name plate-cover-container`
-v "${PWD}/tasks_storage":/app/tasks_storage `  -e "TASK_STORAGE_TTL_HOURS=72"`
plate-cover-service
```

Для Windows (старый cmd.exe):

```bash
docker run -d -p 8000:8000 ^
--name plate-cover-container ^
-v "%cd%/tasks_storage":/app/tasks_storage ^
-e "TASK_STORAGE_TTL_HOURS=72" ^
plate-cover-service
```

Объяснение параметров:

- -d: Запуск в фоновом режиме.

- -p 8000:8000: Проброс порта 8000 из контейнера на ваш компьютер.

- --name: Присвоение удобного имени контейнеру.

- -v ...: Монтирование локальной папки tasks_storage внутрь контейнера для сохранения результатов.

- -e ...: Передача переменных окружения (см. раздел "Конфигурация").

5. Проверьте, что сервис работает:
   Посмотрите логи контейнера, чтобы убедиться в успешном запуске.

```bash
docker logs -f plate-cover-container
```

Теперь ваш сервис доступен по адресу http://localhost:8000.

Документация находится по адресу http://localhost:8000/docs

# Локальная разработка (без Docker)

1. Убедитесь, что у вас установлен Python 3.10+.

2. Перейдите в директорию server/.

3. Создайте и активируйте виртуальное окружение:

```bash
python -m venv venv

# Для Linux/macOS:

source venv/bin/activate

# Для Windows:

venv\Scripts\activate
```

4. Установите зависимости:

```bash
pip install -r requirements.txt
```

5. Установите PyTorch (CPU-версию):

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

6. Запустите сервер для разработки с автоперезагрузкой:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

# Использование API

Полная интерактивная документация доступна по адресу http://localhost:8000/docs.

1. Создание задачи

- Эндпоинт: POST /api/v1/process-task/

- Описание: Отправляет изображения на обработку.

- Запрос: multipart/form-data с полем files, содержащим один или несколько файлов.

- Ответ (202 Accepted): JSON с task_id.

- Пример (cURL):

```bash
curl -X POST "http://localhost:8000/api/v1/process-task/" \
 -F "files=@/path/to/image1.jpg" \
 -F "files=@/path/to/image2.png"
```

Пример ответа:

```json
{ "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef" }
```

2. Проверка статуса задачи

- Эндпоинт: GET /api/v1/task-status/{task_id}

- Описание: Получает текущий статус и результаты задачи.

- Статусы: pending, processing, completed, failed.

- Ответ (200 OK): JSON с полным статусом задачи.

Пример (cURL):

```bash
curl -X GET "http://localhost:8000/api/v1/task-status/a1b2c3d4-e5f6-7890-1234-567890abcdef"
```

Пример ответа (задача завершена):

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "status": "completed",
  "results": [
    {
      "filename": "covered_image1.webp",
      "url": "/tasks_storage/a1b2c3d4.../output/covered_image1.webp"
    }
  ]
}
```

# Конфигурация

Сервис можно настраивать через переменные окружения при запуске Docker-контейнера (-e КЛЮЧ=ЗНАЧЕНИЕ).

переменная - описание - значение по умолчанию
PROCESSING_DEVICE - Устройство для ML-модели (cpu или cuda) - cpu
TASK_STORAGE_TTL_HOURS - Время жизни задач на диске (в часах) - 72
MAX_FILES_PER_REQUEST - Макс. кол-во файлов в одном запросе - 50
PROCESSING_BATCH_SIZE - Размер батча для обработки моделью - 16
