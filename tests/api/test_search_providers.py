"""Reverse-image search provider registry (M5): manual-first, disabled by default."""

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app.services.search_providers import PROVIDERS
from tests.helpers import assert_error


def get_providers(client: TestClient) -> dict:
    response = client.get("/api/v1/search/providers")
    assert response.status_code == 200, response.text
    return response.json()


def test_registry_lists_all_providers_disabled_by_default(client: TestClient) -> None:
    body = get_providers(client)
    assert "sharing that media with the external service" in body["notice"]
    assert [p["key"] for p in body["providers"]] == [
        "google_lens",
        "bing_visual",
        "tineye",
        "yandex_images",
    ]
    for provider in body["providers"]:
        assert provider["enabled"] is False  # 05 §4: external services are disabled by default
        assert provider["instructions"]
        assert provider["terms_url"].startswith("https://")


def test_landing_urls_are_plain_pages_with_no_parameters(client: TestClient) -> None:
    for provider in get_providers(client)["providers"]:
        parsed = urlparse(provider["landing_url"])
        assert parsed.scheme == "https"
        assert parsed.query == "" and parsed.fragment == ""  # nothing evidence-derived, ever
    assert {p.key for p in PROVIDERS} == {"google_lens", "bing_visual", "tineye", "yandex_images"}


def test_enabling_providers_via_settings(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings", json={"enabled_search_providers": ["tineye", "google_lens", "tineye"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["editable"]["enabled_search_providers"] == ["google_lens", "tineye"]

    enabled = {p["key"]: p["enabled"] for p in get_providers(client)["providers"]}
    assert enabled == {"google_lens": True, "bing_visual": False, "tineye": True, "yandex_images": False}

    # Unknown keys are rejected; nothing changes.
    assert_error(
        client.patch("/api/v1/settings", json={"enabled_search_providers": ["askjeeves"]}),
        422,
        "VALIDATION_ERROR",
    )
    assert get_providers(client)["providers"][2]["enabled"] is True


def test_stale_stored_provider_keys_are_ignored_not_crashing(client: TestClient, services, settings) -> None:
    """A stored value that is no longer valid is ignored and the default applies (M2-8 rule)."""
    from app.core.clock import utcnow
    from app.models import AppSetting

    with services.db.writer() as session, session.begin():
        session.merge(
            AppSetting(
                key="enabled_search_providers",
                value=["askjeeves", "tineye"],  # as if a provider was removed in an upgrade
                updated_at=utcnow(),
            )
        )

    body = client.get("/api/v1/settings")
    assert body.status_code == 200, body.text
    assert body.json()["editable"]["enabled_search_providers"] == []  # ignored, default used
    for provider in get_providers(client)["providers"]:
        assert provider["enabled"] is False
