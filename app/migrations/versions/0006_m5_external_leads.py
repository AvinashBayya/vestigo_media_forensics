"""External leads (schema_version 6, Milestone 5: reverse-image search).

Additive only: existing rows are never rewritten.

`external_leads` stores results the analyst found on external search providers and recorded
manually. A lead is an analyst statement, not a machine observation: URLs and the claimed
publication date are kept exactly as entered and never verified. Leads are editable (unlike
machine evidence), so there are no append-only triggers here — every create, update, and delete
is recorded in the append-only custody trail instead (D21).

Revision ID: 0006_m5_external_leads
Revises: 0005_m4b_chain_of_custody
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_m5_external_leads"
down_revision: str | None = "0005_m4b_chain_of_custody"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.create_table(
        "external_leads",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("derived_file_id", sa.String(40), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("result_url", sa.Text(), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("claimed_published_at", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["derived_file_id"], ["derived_files.id"]),
    )
    op.create_index("ix_external_leads_artifact_created", "external_leads", ["artifact_id", "created_at"])
    op.execute("UPDATE schema_meta SET value = '6' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
