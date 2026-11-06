"""Reverse-image search providers (M5): the registry with each provider's enabled state."""

from pydantic import BaseModel


class SearchProviderInfo(BaseModel):
    key: str
    name: str
    landing_url: str
    terms_url: str
    instructions: str
    # Set by the analyst in Settings; every provider starts disabled (05 §4).
    enabled: bool


class SearchProvidersResponse(BaseModel):
    # The sharing warning, shown before any provider page is opened.
    notice: str
    providers: list[SearchProviderInfo]
