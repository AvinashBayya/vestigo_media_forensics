from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.search import SearchProviderInfo, SearchProvidersResponse
from app.services import app_settings
from app.services.search_providers import PROVIDERS, SHARING_WARNING

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/providers", response_model=SearchProvidersResponse)
def list_search_providers(services: Services) -> SearchProvidersResponse:
    """The reverse-image search provider registry (M5). Manual workflows only: landing pages with
    no evidence-derived parameters. A provider is enabled per analyst choice in Settings."""
    enabled = set(app_settings.get_settings_response(services).editable.enabled_search_providers)
    return SearchProvidersResponse(
        notice=SHARING_WARNING,
        providers=[
            SearchProviderInfo(**provider.model_dump(), enabled=provider.key in enabled)
            for provider in PROVIDERS
        ],
    )
