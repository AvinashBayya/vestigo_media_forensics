"""Location candidates (schema_version 7, Milestone 6: GEOINT / geo-lite).

Additive only: existing rows are never rewritten.

`location_candidates` stores possible locations the analyst recorded — analyst interpretations of
Vestigo-held evidence, classified UNVERIFIED, with the analyst's own assessment label (speculative /
possible / likely; never a machine score). Candidates are editable (unlike machine evidence), so
there are no append-only triggers here — every create, update, and delete is recorded in the
append-only custody trail instead (D21).

Revision ID: 0007_m6_location_candidates
Revises: 0006_m5_external_leads
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_m6_location_candidates"
down_revision: str | None = "0006_m5_external_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.create_table(
        "location_candidates",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("analyst_assessment", sa.String(16), nullable=False),
        sa.Column("supports", sa.JSON(), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_location_candidates_artifact_created", "location_candidates", ["artifact_id", "created_at"]
    )
    op.execute("UPDATE schema_meta SET value = '7' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
