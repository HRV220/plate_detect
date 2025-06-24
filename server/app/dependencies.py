# server/app/dependencies.py
from typing import Optional
from redis.asyncio import Redis # <-- ИЗМЕНЕНИЕ: используем асинхронный клиент

from app.core.processor import NumberPlateCoverer

coverer: Optional[NumberPlateCoverer] = None
redis_client: Optional[Redis] = None # <-- ДОБАВЛЕНО