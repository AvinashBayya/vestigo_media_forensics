"""Milestone 3 video foundation schema (schema_version 3).

- artifacts: `duration_seconds` (decision M3-8), the container-reported duration for videos, NULL for
  images and for every existing row.
- keyframe_fingerprints: perceptual hashes of a video's selected keyframes from its latest successful
  analysis, used by duplicate search across videos and images (M3-4). Deleted with the artifact.

Only adds a column and a table: existing rows are not rewritten.

Revision ID: 0003_m3_video_foundation
Revises: 0002_m2_analyst_workflow
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_m3_video_foundation"
down_revision: str | None = "0002_m2_analyst_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("duration_seconds", sa.Float(), nullable=True))

    op.create_table(
        "keyframe_fingerprints",
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("algorithm", sa.String(32), nullable=False),
        sa.Column("frame_seq", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("value_hex", sa.String(64), nullable=False),
        sa.Column("evidence_id", sa.String(40), nullable=False),
        sa.Column("derived_file_id", sa.String(40), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("artifact_id", "algorithm", "frame_seq"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["derived_file_id"], ["derived_files.id"], ondelete="CASCADE"),
    )

    op.execute("UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
