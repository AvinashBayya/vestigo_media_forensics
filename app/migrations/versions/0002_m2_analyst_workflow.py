"""Milestone 2 analyst workflow schema (schema_version 2).

- artifacts: `in_duplicate_library` (decision M2-7); indexes for Library sorting and filtering.
- evidence_records: per-record `analyst_notes` and `review_updated_at` (decision M2-2).
- review_events: append-only review history with full note text (decision M2-3). Triggers reject
  updates, and deletes while the artifact still exists, so only deleting the artifact removes events.
- app_settings: analyst-editable settings (decision M2-8).

Only adds columns, tables, indexes, and triggers: existing rows are not rewritten.

Revision ID: 0002_m2_analyst_workflow
Revises: 0001_m1_baseline
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_m2_analyst_workflow"
down_revision: str | None = "0001_m1_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)
APPEND_ONLY = "review events are append-only"


def upgrade() -> None:
    op.add_column(
        "artifacts",
        sa.Column("in_duplicate_library", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_artifacts_review_state", "artifacts", ["review_state"])
    op.create_index("ix_artifacts_size_bytes", "artifacts", ["size_bytes"])
    op.create_index(
        "ix_artifacts_original_filename_nocase", "artifacts", [sa.text("original_filename COLLATE NOCASE")]
    )

    op.add_column(
        "evidence_records",
        sa.Column("analyst_notes", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column("evidence_records", sa.Column("review_updated_at", TIMESTAMP, nullable=True))

    op.create_table(
        "review_events",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("evidence_id", sa.String(40), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("from_state", sa.String(16), nullable=False),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("notes_before", sa.Text(), nullable=False),
        sa.Column("notes_after", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_review_events_artifact_created", "review_events", ["artifact_id", "created_at"])
    op.execute(
        "CREATE TRIGGER review_events_no_update BEFORE UPDATE ON review_events "
        f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY}'); END"
    )
    # During an artifact's cascade delete the artifact row is already gone, so the cascade is allowed.
    op.execute(
        "CREATE TRIGGER review_events_no_delete BEFORE DELETE ON review_events "
        "WHEN EXISTS (SELECT 1 FROM artifacts WHERE id = OLD.artifact_id) "
        f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY}'); END"
    )

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.execute("UPDATE schema_meta SET value = '2' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
