"""Playable previews (schema_version 4, decision D19 amending M3-6).

One optional re-encoded viewing copy per video artifact, created on demand so browsers can play
codecs they do not support. A preview is a viewing aid, not evidence: it lives outside the derived
evidence files and the export package, and is deleted with the artifact.

Revision ID: 0004_playable_previews
Revises: 0003_m3_video_foundation
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_playable_previews"
down_revision: str | None = "0003_m3_video_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.create_table(
        "playable_previews",
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("stored_path", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("artifact_id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stored_path"),
    )
    op.execute("UPDATE schema_meta SET value = '4' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
