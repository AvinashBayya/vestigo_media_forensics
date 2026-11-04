"""Alembic migrations (decision M2-1): baseline fidelity, in-place upgrade, and refusal of newer schemas."""

import json
import re
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient

from app.core import migrations
from app.core.config import Settings
from app.core.database import Database
from app.main import create_app
from app.models import Base

M1_SCHEMA = Path(__file__).resolve().parent.parent / "fixtures" / "m1_schema.sql"
T0 = "2026-11-02T09:00:00.000000Z"
T1 = "2026-11-02T09:00:05.000000Z"
ART_A = "art_" + "a" * 32
ART_B = "art_" + "b" * 32
JOB_A = "job_" + "a" * 32
EV_HASH = "ev_" + "1" * 32
EV_PHASH = "ev_" + "2" * 32
DF_A = "df_" + "a" * 32


def statements(sql: str) -> list[str]:
    """DDL statements with comments removed and whitespace collapsed, for comparison."""
    without_comments = re.sub(r"--[^\n]*", "", sql)
    return sorted(" ".join(part.split()) for part in without_comments.split(";") if part.strip())


def schema_ddl(path: Path) -> list[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name != 'alembic_version'"
        ).fetchall()
    return statements(";".join(row[0] for row in rows))


def build_m1_database(path: Path) -> None:
    """A database as Milestone 1 left it: the frozen schema, schema_version 1, and data in every table."""
    with sqlite3.connect(path) as connection:
        connection.executescript(M1_SCHEMA.read_text())
        connection.execute("INSERT INTO schema_meta VALUES ('schema_version', '1')")
        for artifact_id, name, state, notes in (
            (ART_A, "harbour.jpg", "REVIEWED", "Checked against source.\nSecond line, ünïcode."),
            (ART_B, "copy.png", "UNREVIEWED", ""),
        ):
            connection.execute(
                "INSERT INTO artifacts VALUES "
                "(?, ?, 'image', 'image/jpeg', 1234, ?, ?, 640, 480, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    name,
                    artifact_id[4:].ljust(64, "0"),
                    artifact_id[4:].ljust(32, "0"),
                    f"artifacts/{artifact_id}/original/{artifact_id}.jpg",
                    state,
                    notes,
                    T1,
                    T0,
                ),
            )
        connection.execute(
            "INSERT INTO analysis_jobs VALUES "
            "(?, ?, 'image.v1', '0.1.0', 'completed', ?, ?, ?, ?, NULL, NULL)",
            (JOB_A, ART_A, json.dumps({"ocr": True, "metadata": True}), T0, T0, T1),
        )
        for evidence_id, stage, payload in (
            (EV_HASH, "hashes", {"sha256": "a" * 64}),
            (EV_PHASH, "perceptual_hash", {"algorithm": "pHash", "bits": 64, "value": "ca13b1cc4cfd4ad2"}),
        ):
            connection.execute(
                "INSERT INTO evidence_records VALUES "
                "(?, ?, ?, ?, 'succeeded', 'DERIVED', 'method', 'artifact:original', 'tool', '1.0', "
                "?, '[]', ?, 'UNREVIEWED', ?, ?)",
                (evidence_id, ART_A, JOB_A, stage, json.dumps(payload), json.dumps(["Limitation."]), T0, T1),
            )
        connection.execute(
            "INSERT INTO derived_files VALUES (?, ?, ?, 'metadata', 'exiftool_json', ?, ?, 10, ?)",
            (DF_A, ART_A, JOB_A, f"artifacts/{ART_A}/derived/{JOB_A}/metadata.exiftool.json", "f" * 64, T1),
        )
        connection.execute(
            "INSERT INTO image_fingerprints VALUES (?, 'phash64', 'ca13b1cc4cfd4ad2', ?, ?)",
            (ART_A, EV_PHASH, T1),
        )


M1_TABLES = {
    "artifacts": "id, original_filename, media_type, mime_type, size_bytes, sha256, md5, width, height, "
    "stored_path, review_state, analyst_notes, review_updated_at, created_at",
    "analysis_jobs": "id, artifact_id, pipeline, app_version, status, options_json, created_at, started_at, "
    "completed_at, error_code, error_message",
    "evidence_records": "id, artifact_id, job_id, stage, status, classification, method, source, tool, "
    "tool_version, payload_json, errors_json, limitations_json, review_state, started_at, completed_at",
    "derived_files": "id, artifact_id, job_id, stage, kind, stored_path, sha256, size_bytes, created_at",
    "image_fingerprints": "artifact_id, algorithm, value_hex, evidence_id, created_at",
    "schema_meta": "key, value",
}


def m1_rows(path: Path) -> dict[str, list[tuple]]:
    """Every row of every Milestone 1 table, restricted to the Milestone 1 columns."""
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT {columns} FROM {table} ORDER BY 1, 2").fetchall()
            for table, columns in M1_TABLES.items()
        }


def revision_in(path: Path) -> str | None:
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "alembic_version" not in tables:
            return None
        return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def test_baseline_revision_reproduces_the_milestone_1_schema(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    with db.engine.connect() as connection, connection.begin():
        command.upgrade(migrations.alembic_config(connection), migrations.BASELINE_REVISION)
    db.dispose()

    assert schema_ddl(tmp_path / "app.db") == statements(M1_SCHEMA.read_text())
    with sqlite3.connect(tmp_path / "app.db") as connection:
        rows = connection.execute("SELECT key, value FROM schema_meta").fetchall()
    assert rows == [("schema_version", "1")]


def test_new_database_is_created_at_the_head_revision(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")

    assert db.initialize() == migrations.head_revision()
    assert db.initialize() == migrations.head_revision()  # idempotent
    assert db.is_healthy()
    db.dispose()
    assert revision_in(tmp_path / "app.db") == migrations.head_revision()


# Alembic reflects SQLite expression indexes as plain column indexes, so it would always report this
# one as changed. Its exact definition is checked separately below.
EXPRESSION_INDEXES = {"ix_artifacts_original_filename_nocase"}


def _index_name(difference: tuple) -> str | None:
    return getattr(difference[1], "name", None) if difference[0] in ("add_index", "remove_index") else None


def test_models_match_the_head_revision(tmp_path: Path) -> None:
    db = Database(tmp_path / "app.db")
    db.initialize()
    with db.engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    db.dispose()
    assert [d for d in differences if _index_name(d) not in EXPRESSION_INDEXES] == []
    with sqlite3.connect(tmp_path / "app.db") as connection:
        (sql,) = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'ix_artifacts_original_filename_nocase'"
        ).fetchone()
    assert " ".join(sql.split()) == (
        "CREATE INDEX ix_artifacts_original_filename_nocase ON artifacts (original_filename COLLATE NOCASE)"
    )


def test_milestone_1_database_is_upgraded_in_place_without_data_loss(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    path = data_dir / "app.db"
    build_m1_database(path)
    before = m1_rows(path)
    assert revision_in(path) is None

    db = Database(path)
    assert db.initialize() == migrations.head_revision()
    assert db.is_healthy()
    db.dispose()

    after = m1_rows(path)
    assert after.pop("schema_meta") == [("schema_version", "4")]
    before.pop("schema_meta")
    assert after == before
    assert revision_in(path) == migrations.head_revision()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    # The upgraded database works through the API.
    settings = Settings(_env_file=None, data_dir=data_dir, job_mode="inline")
    with TestClient(create_app(settings)) as client:
        listed = client.get("/api/v1/artifacts").json()
        assert {item["artifact_id"] for item in listed["items"]} == {ART_A, ART_B}
        detail = client.get(f"/api/v1/artifacts/{ART_A}").json()
        assert detail["review"]["analyst_notes"] == "Checked against source.\nSecond line, ünïcode."
        report = client.get(f"/api/v1/artifacts/{ART_A}/evidence").json()
        assert report["job_id"] == JOB_A
        assert report["perceptual_hash"]["value"] == "ca13b1cc4cfd4ad2"


def test_failed_upgrade_leaves_a_milestone_1_database_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "app.db"
    build_m1_database(path)
    before = m1_rows(path)
    schema_before = schema_ddl(path)

    def failing_upgrade(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated failure during upgrade")

    monkeypatch.setattr(migrations.command, "upgrade", failing_upgrade)
    db = Database(path)
    with pytest.raises(RuntimeError, match="simulated failure"):
        db.initialize()
    db.dispose()

    assert revision_in(path) is None  # the baseline stamp was rolled back too
    assert schema_ddl(path) == schema_before
    assert m1_rows(path) == before


def test_newer_schema_is_refused_and_left_unchanged(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    db = Database(data_dir / "app.db")
    db.initialize()
    db.dispose()
    with sqlite3.connect(data_dir / "app.db") as connection:
        connection.execute("UPDATE alembic_version SET version_num = '9999_from_the_future'")
    schema_before = schema_ddl(data_dir / "app.db")

    db = Database(data_dir / "app.db")
    with pytest.raises(migrations.SchemaError, match="newer than this version of Vestigo supports"):
        db.initialize()
    assert not db.is_healthy()
    db.dispose()
    assert revision_in(data_dir / "app.db") == "9999_from_the_future"
    assert schema_ddl(data_dir / "app.db") == schema_before

    # The application refuses to start.
    settings = Settings(_env_file=None, data_dir=data_dir, job_mode="inline")
    with pytest.raises(migrations.SchemaError), TestClient(create_app(settings)):
        pass


@pytest.mark.parametrize("schema_version", [None, "2", "0"])
def test_database_without_history_that_is_not_milestone_1_is_refused(
    tmp_path: Path, schema_version: str | None
) -> None:
    path = tmp_path / "app.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE something_else (id INTEGER PRIMARY KEY)")
        if schema_version is not None:
            connection.execute("CREATE TABLE schema_meta (key VARCHAR(64) PRIMARY KEY, value VARCHAR(255))")
            connection.execute("INSERT INTO schema_meta VALUES ('schema_version', ?)", (schema_version,))
    schema_before = schema_ddl(path)

    db = Database(path)
    with pytest.raises(migrations.SchemaError, match="not a Milestone 1 database"):
        db.initialize()
    db.dispose()
    assert revision_in(path) is None
    assert schema_ddl(path) == schema_before


def test_foreign_keys_are_enforced_again_after_migrating(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    build_m1_database(path)
    db = Database(path)
    db.initialize()
    with db.reader() as session:
        assert session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    db.dispose()


# --- Milestone 2 revision (0002_m2_analyst_workflow) ------------------------------------------------


def test_milestone_1_rows_get_milestone_2_defaults(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    build_m1_database(path)
    db = Database(path)
    db.initialize()
    db.dispose()

    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT DISTINCT in_duplicate_library FROM artifacts").fetchall() == [(1,)]
        assert connection.execute(
            "SELECT DISTINCT analyst_notes, review_updated_at, review_state FROM evidence_records"
        ).fetchall() == [("", None, "UNREVIEWED")]
        assert connection.execute("SELECT count(*) FROM review_events").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM app_settings").fetchone() == (0,)


def _insert_review_event(connection: sqlite3.Connection, event_id: str, evidence_id: str | None) -> None:
    connection.execute(
        "INSERT INTO review_events VALUES (?, ?, ?, 'artifact', 'UNREVIEWED', 'IN_REVIEW', '', 'note', ?)",
        (event_id, ART_A, evidence_id, T1),
    )


def test_review_events_are_append_only_until_the_artifact_is_deleted(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    build_m1_database(path)
    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _insert_review_event(connection, "rve_" + "1" * 32, None)
        _insert_review_event(connection, "rve_" + "2" * 32, EV_HASH)
        connection.commit()

        for statement in (
            "UPDATE review_events SET notes_after = 'changed'",
            "DELETE FROM review_events",
            f"DELETE FROM evidence_records WHERE id = '{EV_HASH}'",
        ):
            with pytest.raises(sqlite3.DatabaseError, match="review events are append-only"):
                connection.execute(statement)
        assert connection.execute("SELECT count(*) FROM review_events").fetchone() == (2,)

        connection.execute("DELETE FROM artifacts WHERE id = ?", (ART_A,))
        connection.commit()
        assert connection.execute("SELECT count(*) FROM review_events").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM evidence_records").fetchone() == (0,)


# --- Milestone 3 revision (0003_m3_video_foundation) ------------------------------------------------


def build_m2_database(path: Path) -> None:
    """A database as Milestone 2 left it: v1 data upgraded to revision 0002, plus M2 rows."""
    build_m1_database(path)
    db = Database(path)
    with db.engine.connect() as connection, connection.begin():
        command.stamp(migrations.alembic_config(connection), migrations.BASELINE_REVISION)
        command.upgrade(migrations.alembic_config(connection), "0002_m2_analyst_workflow")
    db.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE artifacts SET in_duplicate_library = 0 WHERE id = ?", (ART_B,))
        connection.execute(
            "UPDATE evidence_records SET analyst_notes = 'hash checked', review_updated_at = ? WHERE id = ?",
            (T1, EV_HASH),
        )
        _insert_review_event(connection, "rve_" + "3" * 32, EV_HASH)
        connection.execute("INSERT INTO app_settings VALUES ('library_page_size', '50', ?)", (T1,))


def m2_rows(path: Path) -> dict[str, list[tuple]]:
    tables = dict(
        M1_TABLES,
        review_events="id, artifact_id, evidence_id, origin, from_state, to_state, notes_before, "
        "notes_after, created_at",
        app_settings="key, value_json, updated_at",
    )
    tables["artifacts"] += ", in_duplicate_library"
    tables["evidence_records"] += ", analyst_notes, review_updated_at"
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT {columns} FROM {table} ORDER BY 1, 2").fetchall()
            for table, columns in tables.items()
        }


def test_milestone_2_database_is_upgraded_in_place_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    build_m2_database(path)
    assert revision_in(path) == "0002_m2_analyst_workflow"
    before = m2_rows(path)

    db = Database(path)
    assert db.initialize() == migrations.head_revision()
    assert db.is_healthy()
    db.dispose()

    after = m2_rows(path)
    assert after.pop("schema_meta") == [("schema_version", "4")]
    before.pop("schema_meta")
    assert after == before
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_milestone_3_defaults_and_keyframe_cascade(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    build_m1_database(path)
    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("SELECT DISTINCT duration_seconds FROM artifacts").fetchall() == [(None,)]
        assert connection.execute("SELECT count(*) FROM keyframe_fingerprints").fetchone() == (0,)
        connection.execute(
            "INSERT INTO keyframe_fingerprints VALUES (?, 'phash64', 1, 3.02, 'ca13b1cc4cfd4ad2', ?, ?, ?)",
            (ART_A, EV_PHASH, DF_A, T1),
        )
        # Rejected: the fingerprint must reference a real derived file and evidence record.
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO keyframe_fingerprints VALUES (?, 'phash64', 2, 6.02, 'ff', 'ev_nope', ?, ?)",
                (ART_A, DF_A, T1),
            )
        connection.execute("DELETE FROM artifacts WHERE id = ?", (ART_A,))
        connection.commit()
        assert connection.execute("SELECT count(*) FROM keyframe_fingerprints").fetchone() == (0,)


# --- Playable previews (0004) -----------------------------------------------------------------------


def test_playable_previews_table_defaults_and_cascade(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    build_m1_database(path)
    Database(path).initialize()

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("SELECT count(*) FROM playable_previews").fetchone() == (0,)
        connection.execute(
            "INSERT INTO playable_previews VALUES (?, ?, ?, 123, 640, 360, ?)",
            (ART_A, f"artifacts/{ART_A}/preview/preview.mp4", "e" * 64, T1),
        )
        connection.execute("DELETE FROM artifacts WHERE id = ?", (ART_A,))
        connection.commit()
        assert connection.execute("SELECT count(*) FROM playable_previews").fetchone() == (0,)
