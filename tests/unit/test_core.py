import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, select, text

from app.core import ids
from app.core.database import Database
from app.core.logging import log_event
from app.core.storage import Storage, UnsafePathError
from app.models import AnalysisJob, Artifact


def test_ids_are_prefixed_and_validated() -> None:
    artifact_id = ids.new_id(ids.ARTIFACT)

    assert ids.is_valid_id(artifact_id, ids.ARTIFACT)
    assert not ids.is_valid_id(artifact_id, ids.JOB)
    assert not ids.is_valid_id("art_123", ids.ARTIFACT)
    assert not ids.is_valid_id("art_../../etc/passwd", ids.ARTIFACT)


def test_storage_rejects_paths_outside_the_data_directory(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.prepare()

    with pytest.raises(UnsafePathError):
        storage.resolve("../outside.txt")
    with pytest.raises(UnsafePathError):
        storage.artifact_dir("../../etc")
    assert storage.resolve("artifacts/x") == (tmp_path / "data" / "artifacts" / "x").resolve()


def test_storage_prepare_clears_leftover_temp_and_trash(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "data")
    storage.prepare()
    (storage.tmp_dir / "half-upload.part").write_bytes(b"x")
    (storage.trash_dir / "art_old").mkdir()

    storage.prepare()

    assert list(storage.tmp_dir.iterdir()) == []
    assert list(storage.trash_dir.iterdir()) == []


def test_log_event_drops_fields_outside_the_allow_list(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("vestigo.test")
    logger.propagate = True
    with caplog.at_level(logging.INFO, logger="vestigo.test"):
        log_event(logger, logging.INFO, "upload", artifact_id="art_1", filename="secret.jpg")

    assert "artifact_id=art_1" in caplog.text
    assert "secret.jpg" not in caplog.text
    assert "dropped_fields=1" in caplog.text


def _artifact(artifact_id: str) -> Artifact:
    now = datetime.now(UTC)
    return Artifact(
        id=artifact_id,
        original_filename="a.jpg",
        media_type="image",
        mime_type="image/jpeg",
        size_bytes=1,
        sha256="0" * 64,
        md5="0" * 32,
        stored_path=f"artifacts/{artifact_id}/original/{artifact_id}.jpg",
        review_state="UNREVIEWED",
        analyst_notes="",
        review_updated_at=now,
        created_at=now,
    )


def test_database_initializes_with_pragmas_and_cascades(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.initialize()
    db.initialize()  # idempotent
    assert db.is_healthy()

    artifact_id = ids.new_id(ids.ARTIFACT)
    with db.writer() as session, session.begin():
        session.add(_artifact(artifact_id))
        session.flush()
        session.add(
            AnalysisJob(
                id=ids.new_id(ids.JOB),
                artifact_id=artifact_id,
                pipeline="image.v1",
                app_version="0.1.0",
                status="queued",
                options={},
                created_at=datetime.now(UTC),
            )
        )

    with db.reader() as session:
        assert session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        stored = session.get(Artifact, artifact_id)
        assert stored.created_at.tzinfo is not None

    with db.writer() as session, session.begin():
        session.execute(delete(Artifact).where(Artifact.id == artifact_id))

    with db.reader() as session:
        assert session.scalars(select(AnalysisJob)).all() == []
    db.dispose()
