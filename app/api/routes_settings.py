from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.settings import SettingsResponse, SettingsUpdate
from app.services import app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(services: Services) -> SettingsResponse:
    """Editable settings and the read-only environment settings (M2-8)."""
    return app_settings.get_settings_response(services)


@router.patch("", response_model=SettingsResponse)
def update_settings(services: Services, update: SettingsUpdate) -> SettingsResponse:
    """Change any subset of the editable settings. Environment settings are rejected with 422."""
    return app_settings.update_settings(services, update)
