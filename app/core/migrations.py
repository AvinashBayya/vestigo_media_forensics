"""Database migrations with Alembic (decision M2-1), run by the application at startup.

- A new database is created by running every revision.
- A Milestone 1 database (created by `create_all`, `schema_version` 1, no `alembic_version` table) is
  stamped with the baseline revision, which reproduces its schema exactly, and then upgraded in place.
- A database at a revision this code does not know (written by a newer Vestigo) is refused.

Stamping and upgrading run in one transaction, so a failed upgrade leaves the database unchanged.
Foreign-key enforcement is switched off while migrations run: SQLite applies ON DELETE CASCADE when a
table is dropped, and batch migrations rebuild tables by dropping them. Integrity is checked with
`PRAGMA foreign_key_check` before committing.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE_REVISION = "0001_m1_baseline"
# `schema_meta.schema_version` written by Milestone 1, before Alembic.
LEGACY_SCHEMA_VERSION = "1"


class SchemaError(RuntimeError):
    """The database cannot be used by this version of the application."""


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["connection"] = connection
    return config


def script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def head_revision() -> str:
    head = script_directory().get_current_head()
    if head is None:
        raise SchemaError("No database migrations were found.")
    return head


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _is_known(revision: str) -> bool:
    try:
        return script_directory().get_revision(revision) is not None
    except CommandError:
        return False


def _legacy_schema_version(connection: Connection) -> str | None:
    return connection.execute(
        text("SELECT value FROM schema_meta WHERE key = 'schema_version'")
    ).scalar_one_or_none()


def migrate(engine: Engine) -> str:
    """Bring the database to the head revision and return it. Raises SchemaError if it cannot."""
    with engine.connect() as connection:
        raw = connection.connection.driver_connection
        assert raw is not None
        raw.execute("PRAGMA foreign_keys=OFF")
        try:
            with connection.begin():
                _migrate(connection)
                problems = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
                if problems:
                    raise SchemaError(f"Migration left {len(problems)} broken foreign-key references.")
                revision = current_revision(connection)
        finally:
            raw.execute("PRAGMA foreign_keys=ON")
    assert revision is not None
    return revision


def _migrate(connection: Connection) -> None:
    config = alembic_config(connection)
    revision = current_revision(connection)
    tables = set(inspect(connection).get_table_names())

    if revision is None and tables - {"alembic_version"}:
        legacy = _legacy_schema_version(connection) if "schema_meta" in tables else None
        if legacy != LEGACY_SCHEMA_VERSION:
            raise SchemaError(
                "The database has tables but no migration history, and is not a Milestone 1 database "
                f"(schema_version {legacy!r}). It was not changed."
            )
        command.stamp(config, BASELINE_REVISION)
    elif revision is not None and not _is_known(revision):
        raise SchemaError(
            f"The database schema (revision {revision}) is newer than this version of Vestigo supports "
            f"(latest {head_revision()}). Use a newer version of Vestigo. The database was not changed."
        )

    command.upgrade(config, "head")
