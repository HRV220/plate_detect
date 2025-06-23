# server/app/dependencies.py

from typing import Optional

# Импортируем класс для корректной аннотации типов.
from app.core.processor import NumberPlateCoverer


# Эта глобальная переменная будет хранить наш инициализированный сервис.
# Она начинается с None. Асинхронный обработчик 'startup' в main.py
# заполнит ее реальным объектом.
# Другие части приложения (например, task_manager) будут импортировать
# эту переменную, чтобы получить доступ к сервису.
coverer: Optional[NumberPlateCoverer] = None