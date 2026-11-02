from fastapi.testclient import TestClient

from app import __version__
from app.core.config import Settings
from app.core.tools import ToolRegistry
from app.main import create_app


def test_health_returns_ok_with_all_tools(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["database"] == "ok"
    assert body["storage"] == "ok"
    assert set(body["tools"]) == {"exiftool", "tesseract", "ffmpeg", "ffprobe"}
    for tool in body["tools"].values():
        assert tool["status"] == "ok"
        assert tool["version"]
    assert "eng" in body["tools"]["tesseract"]["languages"]
    assert body["checked_at"].endswith("Z")


def test_health_is_degraded_when_an_m1_tool_is_missing(settings: Settings) -> None:
    def which(name: str) -> str | None:
        return None if name == "exiftool" else f"/usr/bin/{name}"

    app = create_app(settings, tools=ToolRegistry(which=which))
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()

    assert body["status"] == "degraded"
    assert body["tools"]["exiftool"] == {
        "status": "missing",
        "version": None,
        "used_in": "M1: metadata, C2PA detection",
        "languages": None,
        "detail": "not found on PATH",
    }


def test_missing_m3_tool_does_not_degrade_health(settings: Settings) -> None:
    def which(name: str) -> str | None:
        return None if name == "ffprobe" else f"/usr/bin/{name}"

    app = create_app(settings, tools=ToolRegistry(which=which))
    with TestClient(app) as client:
        body = client.get("/api/v1/health").json()

    assert body["status"] == "ok"
    assert body["tools"]["ffprobe"]["status"] == "missing"


def test_health_returns_503_when_storage_fails(client: TestClient, services, monkeypatch) -> None:
    monkeypatch.setattr(services.storage, "is_healthy", lambda: False)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["storage"] == "error"
