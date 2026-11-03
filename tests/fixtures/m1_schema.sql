-- Milestone 1 database schema (SQLite), exactly as SQLAlchemy create_all produced it before
-- Alembic was introduced (schema_version 1). Frozen: do not edit. Used by the migration tests to
-- check the Alembic baseline and to build Milestone 1 databases for upgrade tests.

CREATE TABLE analysis_jobs (
	id VARCHAR(40) NOT NULL, 
	artifact_id VARCHAR(40) NOT NULL, 
	pipeline VARCHAR(32) NOT NULL, 
	app_version VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	options_json JSON NOT NULL, 
	created_at VARCHAR(32) NOT NULL, 
	started_at VARCHAR(32), 
	completed_at VARCHAR(32), 
	error_code VARCHAR(64), 
	error_message TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE
);

CREATE TABLE artifacts (
	id VARCHAR(40) NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	media_type VARCHAR(16) NOT NULL, 
	mime_type VARCHAR(32) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	md5 VARCHAR(32) NOT NULL, 
	width INTEGER, 
	height INTEGER, 
	stored_path VARCHAR(255) NOT NULL, 
	review_state VARCHAR(16) NOT NULL, 
	analyst_notes TEXT NOT NULL, 
	review_updated_at VARCHAR(32) NOT NULL, 
	created_at VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_artifacts_size_positive CHECK (size_bytes > 0), 
	CONSTRAINT ck_artifacts_sha256_length CHECK (length(sha256) = 64), 
	CONSTRAINT ck_artifacts_md5_length CHECK (length(md5) = 32), 
	UNIQUE (stored_path)
);

CREATE TABLE derived_files (
	id VARCHAR(40) NOT NULL, 
	artifact_id VARCHAR(40) NOT NULL, 
	job_id VARCHAR(40) NOT NULL, 
	stage VARCHAR(64) NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	stored_path VARCHAR(255) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	created_at VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE, 
	UNIQUE (stored_path)
);

CREATE TABLE evidence_records (
	id VARCHAR(40) NOT NULL, 
	artifact_id VARCHAR(40) NOT NULL, 
	job_id VARCHAR(40) NOT NULL, 
	stage VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	classification VARCHAR(16) NOT NULL, 
	method TEXT NOT NULL, 
	source VARCHAR(128) NOT NULL, 
	tool VARCHAR(128) NOT NULL, 
	tool_version VARCHAR(128), 
	payload_json JSON NOT NULL, 
	errors_json JSON NOT NULL, 
	limitations_json JSON NOT NULL, 
	review_state VARCHAR(16) NOT NULL, 
	started_at VARCHAR(32) NOT NULL, 
	completed_at VARCHAR(32) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_evidence_records_job_stage UNIQUE (job_id, stage), 
	CONSTRAINT ck_evidence_records_limitations CHECK (json_array_length(limitations_json) > 0), 
	FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE, 
	FOREIGN KEY(job_id) REFERENCES analysis_jobs (id) ON DELETE CASCADE
);

CREATE TABLE image_fingerprints (
	artifact_id VARCHAR(40) NOT NULL, 
	algorithm VARCHAR(32) NOT NULL, 
	value_hex VARCHAR(64) NOT NULL, 
	evidence_id VARCHAR(40) NOT NULL, 
	created_at VARCHAR(32) NOT NULL, 
	PRIMARY KEY (artifact_id, algorithm), 
	FOREIGN KEY(artifact_id) REFERENCES artifacts (id) ON DELETE CASCADE, 
	FOREIGN KEY(evidence_id) REFERENCES evidence_records (id) ON DELETE CASCADE
);

CREATE TABLE schema_meta (
	"key" VARCHAR(64) NOT NULL, 
	value VARCHAR(255) NOT NULL, 
	PRIMARY KEY ("key")
);

CREATE INDEX ix_analysis_jobs_artifact_created ON analysis_jobs (artifact_id, created_at);

CREATE INDEX ix_artifacts_created_at ON artifacts (created_at);

CREATE INDEX ix_artifacts_sha256 ON artifacts (sha256);

CREATE INDEX ix_derived_files_artifact_id ON derived_files (artifact_id);

CREATE INDEX ix_evidence_records_artifact_id ON evidence_records (artifact_id);
