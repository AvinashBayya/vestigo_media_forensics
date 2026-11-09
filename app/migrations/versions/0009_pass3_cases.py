"""Cases and case membership (schema_version 9, Pass 3: integration hardening, D26).

Additive only: existing rows are never rewritten, and no existing table is touched.

A case groups artifacts under a name the analyst chose. It is organisation, not evidence: it carries
no classification, asserts nothing about its artifacts, and deleting a case removes only the case
and its links - never an artifact. Linking and unlinking are recorded as append-only custody events
on the artifact, so an artifact's trail shows which cases it was put in and when.

Revision ID: 0009_pass3_cases
Revises: 0008_pass1_local_ai
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_pass3_cases"
down_revision: str | None = "0008_pass1_local_ai"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "case_artifacts",
        sa.Column("case_id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("added_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("case_id", "artifact_id"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_case_artifacts_artifact", "case_artifacts", ["artifact_id"])
    op.execute("UPDATE schema_meta SET value = '9' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
