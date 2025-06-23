# server/app/api/utils/endpoints.py

from fastapi import APIRouter
from fastapi.responses import RedirectResponse
# Импортируем специальные функции для генерации HTML документации
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

router = APIRouter()

@router.get("/", include_in_schema=False)
async def root_redirect():
    """Редирект с корневого URL на страницу документации."""
    return RedirectResponse(url="/docs")

@router.get("/docs", include_in_schema=False)
async def get_swagger_documentation():
    """Отдает HTML страницу для Swagger UI."""
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Docs - Swagger UI")

@router.get("/redoc", include_in_schema=False)
async def get_redoc_documentation():
    """Отдает HTML страницу для ReDoc."""
    return get_redoc_html(openapi_url="/openapi.json", title="API Docs - ReDoc")

@router.get("/health", tags=["Monitoring"])
async def health_check():
    """
    Эндпоинт для проверки работоспособности сервиса (health check).
    """
    return {"status": "ok"}