"""Alembic environment.

The application runs migrations itself at startup (app.core.migrations), passing an open connection in
`config.attributes["connection"]`. For developers, `alembic` on the command line uses the database in
VESTIGO_DATA_DIR (see alembic.ini).
"""

from alembic import context
from sqlalchemy.engine import Connection

from app.models import Base

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline (SQL script) migrations are not supported.")

connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    from app.core.config import get_settings
    from app.core.database import Database

    database = Database(get_settings().data_dir / "app.db")
    with database.engine.connect() as cli_connection:
        run_migrations(cli_connection)
