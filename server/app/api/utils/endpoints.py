# server/app/api/utils/router.py

from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse

router = APIRouter()
# Используем временный экземпляр FastAPI для доступа к хелперам документации
temp_app = FastAPI()

@router.get("/", include_in_schema=False)
async def root_redirect():
    """Редирект с корневого URL на страницу документации."""
    return RedirectResponse(url="/docs")

@router.get("/docs", include_in_schema=False)
async def get_swagger_ui_html():
    """Отдает HTML страницу для Swagger UI."""
    return temp_app.swagger_ui_html(openapi_url="/openapi.json", title="API Docs - Swagger UI")

@router.get("/redoc", include_in_schema=False)
async def get_redoc_html():
    """Отдает HTML страницу для ReDoc."""
    return temp_app.redoc_ui_html(openapi_url="/openapi.json", title="API Docs - ReDoc")

@router.get("/health", tags=["Monitoring"])
async def health_check():
    """
    Эндпоинт для проверки работоспособности сервиса (health check).
    """
    return {"status": "ok"}