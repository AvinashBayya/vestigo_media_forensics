"""Local AI artifacts (schema_version 8, Pass 1: local intelligence foundation, D24).

Additive only: existing rows are never rewritten, and no existing table is touched.

Three tables hold everything a local model produces, deliberately apart from the evidence tables so
that AI output can never be mistaken for evidence:

- `ai_drafts`: fields a model proposed from held material, each accepted, edited, or rejected by the
  analyst. Nothing is ever written back over metadata or evidence.
- `transcripts`: machine transcripts of an artifact's audio, with the model's text kept verbatim
  beside any analyst edit, and the extracted audio track recorded as lineage.
- `embedding_chunks`: rebuildable local search index over the analyst's own text, recording the
  model that produced each vector.

All three carry full model provenance and cascade-delete with their artifact. None has append-only
triggers: these are analyst-editable working records, and the custody trail is the audit (D21).

Revision ID: 0008_pass1_local_ai
Revises: 0007_m6_location_candidates
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_pass1_local_ai"
down_revision: str | None = "0007_m6_location_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.create_table(
        "ai_drafts",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_evidence_id", sa.String(40), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model", sa.JSON(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_evidence_id"], ["evidence_records.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ai_drafts_artifact_created", "ai_drafts", ["artifact_id", "created_at"])

    op.create_table(
        "transcripts",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("derived_file_id", sa.String(40), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("edited_text", sa.Text(), nullable=True),
        sa.Column("model", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["derived_file_id"], ["derived_files.id"]),
    )
    op.create_index("ix_transcripts_artifact_created", "transcripts", ["artifact_id", "created_at"])

    op.create_table(
        "embedding_chunks",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(40), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_embedding_chunks_artifact", "embedding_chunks", ["artifact_id"])
    op.create_index("ix_embedding_chunks_model", "embedding_chunks", ["model_name"])

    op.execute("UPDATE schema_meta SET value = '8' WHERE key = 'schema_version'")


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
