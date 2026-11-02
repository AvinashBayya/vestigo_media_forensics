import hashlib
import io
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.fixtures.make_fixtures import FixtureSet
from tests.helpers import assert_error, upload, upload_ok


@pytest.mark.parametrize(
    ("fixture_name", "mime_type", "extension"),
    [
        ("jpeg", "image/jpeg", "jpg"),
        ("png", "image/png", "png"),
        ("webp", "image/webp", "webp"),
        ("tiff", "image/tiff", "tiff"),
    ],
)
def test_supported_images_upload(
    client: TestClient,
    settings: Settings,
    fixtures: FixtureSet,
    fixture_name: str,
    mime_type: str,
    extension: str,
) -> None:
    path: Path = getattr(fixtures, fixture_name)

    body = upload_ok(client, path)

    assert body["artifact_id"].startswith("art_")
    assert body["filename"] == path.name
    assert body["media_type"] == "image"
    assert body["mime_type"] == mime_type
    assert body["size_bytes"] == path.stat().st_size
    assert body["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert body["created_at"].endswith("Z")

    stored = (
        settings.data_dir
        / "artifacts"
        / body["artifact_id"]
        / "original"
        / f"{body['artifact_id']}.{extension}"
    )
    assert stored.read_bytes() == path.read_bytes()
    assert stat.S_IMODE(stored.stat().st_mode) == 0o444


@pytest.mark.parametrize("fixture_name", ["gif", "html_named_jpg"])
def test_unsupported_types_are_rejected(client: TestClient, fixtures: FixtureSet, fixture_name: str) -> None:
    assert_error(upload(client, getattr(fixtures, fixture_name)), 415, "UNSUPPORTED_MEDIA_TYPE")


def test_unreadable_image_is_rejected(client: TestClient, fixtures: FixtureSet) -> None:
    assert_error(upload(client, fixtures.truncated_jpeg), 422, "INVALID_IMAGE")


@pytest.mark.parametrize("fixture_name", ["oversized_dimensions", "bomb_dimensions"])
def test_images_over_the_pixel_limit_are_rejected(
    client: TestClient, fixtures: FixtureSet, fixture_name: str
) -> None:
    error = assert_error(upload(client, getattr(fixtures, fixture_name)), 422, "IMAGE_TOO_LARGE")
    assert error["details"] == {"max_pixels": 100_000_000}


def test_empty_file_is_rejected(client: TestClient) -> None:
    files = {"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")}
    assert_error(client.post("/api/v1/artifacts/upload", files=files), 400, "EMPTY_FILE")


def test_missing_file_is_rejected(client: TestClient) -> None:
    assert_error(client.post("/api/v1/artifacts/upload", data={"other": "x"}), 400, "MISSING_FILE")


def test_oversized_file_is_rejected_and_nothing_is_kept(tmp_path: Path, fixtures: FixtureSet) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", job_mode="inline", max_upload_bytes=1000)
    with TestClient(create_app(settings)) as client:
        # Within the multipart allowance, so the size is caught while copying the file.
        error = assert_error(upload(client, fixtures.jpeg), 413, "FILE_TOO_LARGE")
        assert error["details"] == {"max_bytes": 1000}

        # Far above the limit, so the request is refused before the body is parsed.
        files = {"file": ("big.jpg", io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 200_000), "image/jpeg")}
        assert_error(client.post("/api/v1/artifacts/upload", files=files), 413, "FILE_TOO_LARGE")

        assert list((settings.data_dir / "tmp").iterdir()) == []
        assert list((settings.data_dir / "artifacts").iterdir()) == []


@pytest.mark.parametrize(
    ("client_filename", "stored_name"),
    [
        ("../../etc/passwd.jpg", "passwd.jpg"),
        ("..\\..\\windows\\evil.jpg", "evil.jpg"),
        ("/absolute/path/photo.jpg", "photo.jpg"),
        ("innocent‮gpj.exe", "innocentgpj.exe"),
        ("..", "upload"),
    ],
)
def test_client_filenames_cannot_escape_storage(
    client: TestClient,
    settings: Settings,
    fixtures: FixtureSet,
    tmp_path: Path,
    client_filename: str,
    stored_name: str,
) -> None:
    body = upload_ok(client, fixtures.jpeg, filename=client_filename)

    assert body["filename"] == stored_name
    artifact_dir = settings.data_dir / "artifacts" / body["artifact_id"]
    stored_files = [p for p in artifact_dir.rglob("*") if p.is_file()]
    assert len(stored_files) == 1
    assert stored_files[0].resolve().is_relative_to(settings.data_dir.resolve())
    assert not (tmp_path / "etc").exists()


def test_same_file_uploaded_twice_creates_two_artifacts(client: TestClient, fixtures: FixtureSet) -> None:
    first = upload_ok(client, fixtures.jpeg)
    second = upload_ok(client, fixtures.jpeg)

    assert first["artifact_id"] != second["artifact_id"]
    assert first["sha256"] == second["sha256"]


def test_list_and_detail(client: TestClient, fixtures: FixtureSet) -> None:
    first = upload_ok(client, fixtures.jpeg)
    second = upload_ok(client, fixtures.png)

    listing = client.get("/api/v1/artifacts").json()
    assert listing["total"] == 2
    assert [item["artifact_id"] for item in listing["items"]] == [second["artifact_id"], first["artifact_id"]]
    assert listing["items"][0]["latest_job_status"] is None

    page = client.get("/api/v1/artifacts", params={"limit": 1, "offset": 1}).json()
    assert [item["artifact_id"] for item in page["items"]] == [first["artifact_id"]]

    detail = client.get(f"/api/v1/artifacts/{first['artifact_id']}").json()
    assert detail["sha256"] == first["sha256"]
    assert detail["md5"] == hashlib.md5(fixtures.jpeg.read_bytes()).hexdigest()
    assert (detail["width"], detail["height"]) == (640, 480)
    assert detail["review"]["state"] == "UNREVIEWED"
    assert detail["latest_job"] is None


@pytest.mark.parametrize("artifact_id", ["art_" + "0" * 32, "not-an-id", "art_../../etc"])
def test_unknown_or_malformed_artifact_id_returns_404(client: TestClient, artifact_id: str) -> None:
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}"), 404, "ARTIFACT_NOT_FOUND")
    assert_error(client.get(f"/api/v1/artifacts/{artifact_id}/content"), 404, "ARTIFACT_NOT_FOUND")


def test_content_returns_original_bytes_with_safe_headers(client: TestClient, fixtures: FixtureSet) -> None:
    body = upload_ok(client, fixtures.png)

    response = client.get(f"/api/v1/artifacts/{body['artifact_id']}/content")

    assert response.status_code == 200
    assert response.content == fixtures.png.read_bytes()
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.headers["content-disposition"].startswith("inline")


def test_review_state_can_be_updated(client: TestClient, fixtures: FixtureSet) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]

    response = client.patch(
        f"/api/v1/artifacts/{artifact_id}/review", json={"state": "FLAGGED", "analyst_notes": "Check source."}
    )

    assert response.status_code == 200
    review = response.json()["review"]
    assert review["state"] == "FLAGGED"
    assert review["analyst_notes"] == "Check source."
    assert client.get(f"/api/v1/artifacts/{artifact_id}").json()["review_state"] == "FLAGGED"


@pytest.mark.parametrize(
    "payload",
    [{"state": "AUTHENTIC"}, {"state": "REVIEWED", "verdict": "real"}, {"analyst_notes": "no state"}],
)
def test_invalid_review_update_is_rejected(client: TestClient, fixtures: FixtureSet, payload: dict) -> None:
    artifact_id = upload_ok(client, fixtures.jpeg)["artifact_id"]
    assert_error(
        client.patch(f"/api/v1/artifacts/{artifact_id}/review", json=payload), 422, "VALIDATION_ERROR"
    )


def test_review_update_for_unknown_artifact_returns_404(client: TestClient) -> None:
    response = client.patch(f"/api/v1/artifacts/art_{'0' * 32}/review", json={"state": "REVIEWED"})
    assert_error(response, 404, "ARTIFACT_NOT_FOUND")
