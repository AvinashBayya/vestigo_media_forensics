"""Duplicate and near-duplicate search over the local library."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from app.core.database import Database
from app.models import Artifact, ImageFingerprint
from app.services.phash import BITS, hamming_distance

MatchType = Literal["exact_file", "visually_identical", "near"]


@dataclass(frozen=True)
class LibraryEntry:
    artifact_id: str
    sha256: str
    perceptual_hash: str | None


class LibraryReader:
    """Read access to the local artifact library, for duplicate search."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def snapshot(self, artifact_id: str, algorithm: str) -> "LibrarySnapshot":
        """Every other artifact in the duplicate library, and how many the analyst excluded (M2-7)."""
        stmt = (
            select(Artifact.id, Artifact.sha256, ImageFingerprint.value_hex, Artifact.in_duplicate_library)
            .outerjoin(
                ImageFingerprint,
                (ImageFingerprint.artifact_id == Artifact.id) & (ImageFingerprint.algorithm == algorithm),
            )
            .where(Artifact.id != artifact_id)
        )
        with self._db.reader() as session:
            rows = session.execute(stmt).all()
        entries = [LibraryEntry(row[0], row[1], row[2]) for row in rows if row[3]]
        return LibrarySnapshot(entries=entries, excluded_count=len(rows) - len(entries))


@dataclass(frozen=True)
class LibrarySnapshot:
    entries: list[LibraryEntry]
    # Artifacts left out because the analyst excluded them from duplicate search.
    excluded_count: int


@dataclass(frozen=True)
class DuplicateCandidate:
    """A match. Only the matched artifact's ID is kept, so deleting that artifact leaves no trace of
    its filename here; the evidence report looks the filename up when it is built."""

    artifact_id: str
    distance: int
    similarity: float
    match_type: MatchType


@dataclass(frozen=True)
class SearchResult:
    matches: list[DuplicateCandidate]
    library_size: int
    compared: int


def find_matches(
    sha256: str, perceptual_hash: str, library: Iterable[LibraryEntry], threshold: int
) -> SearchResult:
    """Byte-identical files match by SHA-256; others match when the pHash distance is within the threshold."""
    matches: list[DuplicateCandidate] = []
    library_size = compared = 0
    for entry in library:
        library_size += 1
        if entry.sha256 == sha256:
            matches.append(DuplicateCandidate(entry.artifact_id, 0, 1.0, "exact_file"))
            continue
        if entry.perceptual_hash is None:
            continue
        compared += 1
        distance = hamming_distance(perceptual_hash, entry.perceptual_hash)
        if distance <= threshold:
            match_type: MatchType = "visually_identical" if distance == 0 else "near"
            similarity = round(1 - distance / BITS, 4)
            matches.append(DuplicateCandidate(entry.artifact_id, distance, similarity, match_type))
    matches.sort(key=lambda match: (match.distance, match.match_type != "exact_file", match.artifact_id))
    return SearchResult(matches, library_size, compared)
