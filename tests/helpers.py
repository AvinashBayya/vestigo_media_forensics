from pathlib import Path

from fastapi.testclient import TestClient
from httpx import Response


def upload(client: TestClient, path: Path, filename: str | None = None) -> Response:
    with path.open("rb") as stream:
        files = {"file": (filename or path.name, stream, "application/octet-stream")}
        return client.post("/api/v1/artifacts/upload", files=files)


def upload_ok(client: TestClient, path: Path, filename: str | None = None) -> dict:
    response = upload(client, path, filename)
    assert response.status_code == 201, response.text
    return response.json()


def assert_error(response: Response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]
