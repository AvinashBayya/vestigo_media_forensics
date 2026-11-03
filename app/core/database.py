"""SQLite engine and sessions.

Read sessions use SQLite's default deferred transactions, so they never block. Write sessions start
with BEGIN IMMEDIATE, which takes the write lock up front: two writers then queue on busy_timeout
instead of failing with "database is locked" when one upgrades a read to a write. Callers keep
write transactions short and never hold one open while a tool runs.
"""

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core import migrations


def _on_connect(dbapi_connection: Any, _: Any) -> None:
    # Let SQLAlchemy's "begin" event issue BEGIN instead of the sqlite3 driver.
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    for pragma in (
        "PRAGMA foreign_keys=ON",
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=5000",
        "PRAGMA synchronous=NORMAL",
    ):
        cursor.execute(pragma)
    cursor.close()


def _on_begin(connection: Connection) -> None:
    mode = connection.get_execution_options().get("sqlite_begin", "DEFERRED")
    connection.exec_driver_sql(f"BEGIN {mode}")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        event.listen(self.engine, "connect", _on_connect)
        event.listen(self.engine, "begin", _on_begin)
        self._reader = sessionmaker(self.engine, expire_on_commit=False)
        self._writer = sessionmaker(
            self.engine.execution_options(sqlite_begin="IMMEDIATE"), expire_on_commit=False
        )

    def reader(self) -> Session:
        return self._reader()

    def writer(self) -> Session:
        """Use as `with db.writer() as session, session.begin(): ...`."""
        return self._writer()

    def initialize(self) -> str:
        """Create or migrate the database to the latest schema. Returns the schema revision."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return migrations.migrate(self.engine)

    def is_healthy(self) -> bool:
        try:
            with self.reader() as session:
                return migrations.current_revision(session.connection()) == migrations.head_revision()
        except (SQLAlchemyError, migrations.SchemaError):
            return False

    def dispose(self) -> None:
        self.engine.dispose()
