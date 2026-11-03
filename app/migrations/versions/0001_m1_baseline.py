"""Milestone 1 baseline: the schema as created before Alembic (schema_version 1).

Frozen. It must keep producing exactly tests/fixtures/m1_schema.sql, so that a database created by
Milestone 1 and a database created by this revision are the same.

Revision ID: 0001_m1_baseline
Revises:
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_m1_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# UTC timestamps are stored as ISO-8601 text (app.models.base.UTCDateTime).
TIMESTAMP = sa.String(32)


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("pipeline", sa.String(32), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("completed_at", TIMESTAMP, nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("md5", sa.String(32), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("stored_path", sa.String(255), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("analyst_notes", sa.Text(), nullable=False),
        sa.Column("review_updated_at", TIMESTAMP, nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("size_bytes > 0", name="ck_artifacts_size_positive"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_artifacts_sha256_length"),
        sa.CheckConstraint("length(md5) = 32", name="ck_artifacts_md5_length"),
        sa.UniqueConstraint("stored_path"),
    )
    op.create_table(
        "derived_files",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("job_id", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("stored_path", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stored_path"),
    )
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("job_id", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("tool", sa.String(128), nullable=False),
        sa.Column("tool_version", sa.String(128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("errors_json", sa.JSON(), nullable=False),
        sa.Column("limitations_json", sa.JSON(), nullable=False),
        sa.Column("review_state", sa.String(16), nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.Column("completed_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "stage", name="uq_evidence_records_job_stage"),
        sa.CheckConstraint("json_array_length(limitations_json) > 0", name="ck_evidence_records_limitations"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["analysis_jobs.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "image_fingerprints",
        sa.Column("artifact_id", sa.String(40), nullable=False),
        sa.Column("algorithm", sa.String(32), nullable=False),
        sa.Column("value_hex", sa.String(64), nullable=False),
        sa.Column("evidence_id", sa.String(40), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("artifact_id", "algorithm"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_records.id"], ondelete="CASCADE"),
    )
    schema_meta = op.create_table(
        "schema_meta",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_analysis_jobs_artifact_created", "analysis_jobs", ["artifact_id", "created_at"])
    op.create_index("ix_artifacts_created_at", "artifacts", ["created_at"])
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"])
    op.create_index("ix_derived_files_artifact_id", "derived_files", ["artifact_id"])
    op.create_index("ix_evidence_records_artifact_id", "evidence_records", ["artifact_id"])
    op.bulk_insert(schema_meta, [{"key": "schema_version", "value": "1"}])


def downgrade() -> None:
    raise NotImplementedError("Vestigo does not support schema downgrades.")
