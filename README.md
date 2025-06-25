Сервис для анонимизации номерных знаков v1.0

![alt text](https://img.shields.io/badge/Python-3.11-blue.svg)

![alt text](https://img.shields.io/badge/FastAPI-0.115-green.svg)

![alt text](https://img.shields.io/badge/Redis-Ready-red.svg)

![alt text](https://img.shields.io/badge/Docker-Compose-blue.svg)

![alt text](https://img.shields.io/badge/License-MIT-lightgrey.svg)

Продакшен-готовый, масштабируемый и отказоустойчивый сервис на FastAPI и Redis для детекции автомобильных номеров на изображениях и наложения на них кастомной заглушки.

# Ключевые возможности

- Асинхронность и масштабируемость: Сервис мгновенно принимает задачи и обрабатывает их в фоновом режиме. Благодаря Redis для управления состоянием, сервис легко масштабируется на несколько рабочих процессов или серверов.

- Пакетная обработка: Эффективная обработка до 50 изображений за один запрос для максимальной производительности.

- Высокая производительность: Использует оптимизированную модель YOLOv8-OBB и ThreadPoolExecutor для распараллеливания I/O операций.

- Поддержка форматов: Принимает изображения JPEG, PNG, WebP и отдает результаты в экономичном формате WebP.

- Надежность: Профессиональная архитектура, централизованная конфигурация, полное логирование и обработка ошибок.

- Готовность к развертыванию: Упакован в Docker-контейнер и управляется через Docker Compose для легкого и безопасного деплоя одной командой.

- Автоматическая очистка: Задачи автоматически удаляются из хранилища по истечении TTL, настроенного в Redis.

- Автоматическая документация: Интерактивная документация API доступна через Swagger UI (/docs) и ReDoc (/redoc).

# Технологический стек

- Фреймворк: FastAPI

- Сервер: Gunicorn + Uvicorn

- Управление состоянием: Redis

- ML-модель: YOLOv8-OBB (Ultralytics)

- Обработка изображений: OpenCV, Pillow

- Валидация данных: Pydantic

- Контейнеризация: Docker, Docker Compose

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
| ├── docker-compose.yml  # Файл для оркестрации сервиса и Redis
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

Создайте файл .env

2. Соберите Docker-образ:
   Эта команда прочитает Dockerfile и соберет самодостаточный образ приложения.

```bash
docker-compose up --build -d
```

4. Проверьте, что сервис работает:
   Посмотрите логи, чтобы убедиться в успешном запуске обоих сервисов.

```bash
docker-compose logs -f
```

# Остановка сервиса

Чтобы остановить и удалить контейнеры, выполните:

```bash
docker-compose down
```

Для удаления томов (включая tasks_storage), добавьте флаг -v:

```bash
docker-compose down -v
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

PROCESSING_DEVICE - Устройство для ML-модели (cpu или cuda) - cpu;

TASK_STORAGE_TTL_HOURS - Время жизни задач на диске (в часах) - 72;

MAX_FILES_PER_REQUEST - Макс. кол-во файлов в одном запросе - 50;

PROCESSING_BATCH_SIZE - Размер батча для обработки моделью - 16;
