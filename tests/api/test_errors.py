from fastapi.testclient import TestClient


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    assert_error(client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND")


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    assert_error(client.delete("/api/v1/health"), 405, "METHOD_NOT_ALLOWED")
