from fastapi.testclient import TestClient

from tests.helpers import assert_error


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    assert_error(client.get("/api/v1/does-not-exist"), 404, "NOT_FOUND")


def test_wrong_method_uses_error_envelope(client: TestClient) -> None:
    assert_error(client.delete("/api/v1/health"), 405, "METHOD_NOT_ALLOWED")
