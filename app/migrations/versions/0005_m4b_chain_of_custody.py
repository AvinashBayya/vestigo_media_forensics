"""Chain of custody (schema_version 5, Milestone 4 part 2).

Additive only: existing rows are never rewritten.

- `custody_events` records the actions that previously left no trace: evidence-package exports,
  duplicate-library include/exclude changes, and playable-preview creation. Upload, analysis jobs,
  evidence records, and review events stay in their own tables; the custody timeline merges all
  sources at read time. Append-only like `review_events`: the database rejects updates and deletes,
  except the cascade when the artifact itself is deleted. Exports and library changes made before
  this revision were not recorded anywhere and are NOT backfilled — inventing history would be
  fabrication.
- `derived_files` gains nullable `source_kind` ("original" or "derived_file") and
  `source_derived_file_id`, recording what each new derived file was made from. Rows written before
  this revision keep NULL and are reported as "source not recorded", never guessed.

Revision ID: 0005_m4b_chain_of_custody
Revises: 0004_playable_previews
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_m4b_chain_of_custody"
down_revision: str | None = "0004_playable_previews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)
APPEND_ONLY = "custody events are append-only"


def upgrade() -> None:
    op.create_table(
        "custody_events",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_custody_events_artifact_created", "custody_events", ["artifact_id", "created_at"])
    op.execute(
        "CREATE TRIGGER custody_events_no_update BEFORE UPDATE ON custody_events "
        f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY}'); END"
    )
    # During an artifact's cascade delete the artifact row is already gone, so the cascade is allowed.
    op.execute(
        "CREATE TRIGGER custody_events_no_delete BEFORE DELETE ON custody_events "
        "WHEN EXISTS (SELECT 1 FROM artifacts WHERE id = OLD.artifact_id) "
        f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY}'); END"
    )

    with op.batch_alter_table("derived_files") as batch:
        batch.add_column(sa.Column("source_kind", sa.String(16), nullable=True))
        batch.add_column(sa.Column("source_derived_file_id", sa.String(40), nullable=True))
        batch.create_foreign_key(
            "fk_derived_files_source", "derived_files", ["source_derived_file_id"], ["id"]
        )

    op.execute("UPDATE schema_meta SET value = '5' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
