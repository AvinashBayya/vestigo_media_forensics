"""Duplicate-library management (decision M2-7)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DuplicateLibraryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # False excludes the artifact from future duplicate searches. Existing evidence is not changed.
    included: bool


class LibraryArtifactRef(BaseModel):
    artifact_id: str
    filename: str
    created_at: datetime
    # True if the artifact has a perceptual hash (it has been analysed).
    indexed: bool


class StorageUsage(BaseModel):
    # Sizes recorded in the database: uploaded originals, files derived during analysis, and
    # playable viewing copies (D19).
    original_bytes: int
    derived_bytes: int
    preview_bytes: int = 0


class LibrarySummary(BaseModel):
    artifact_count: int
    # Included in duplicate search and analysed (has a perceptual hash).
    indexed_count: int
    # Included but never analysed: found by future searches only if byte-identical.
    not_indexed_count: int
    excluded_count: int
    # Up to LIST_LIMIT of each, newest first.
    not_indexed: list[LibraryArtifactRef]
    excluded: list[LibraryArtifactRef]
    storage: StorageUsage
