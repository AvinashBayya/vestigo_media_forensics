"""Duplicate and near-duplicate search over the local library (M2-7, M3-4).

From Milestone 3 the search spans media types: an image's pHash and a video's keyframe pHashes are
compared with every other artifact's image hash and keyframe hashes. Byte-identical files always
match by SHA-256. Artifacts the analyst excluded from the duplicate library are skipped entirely and
only counted.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select

from app.core.database import Database
from app.models import Artifact, ImageFingerprint, KeyframeFingerprint
from app.services.phash import BITS, hamming_distance

MatchType = Literal["exact_file", "visually_identical", "near"]


@dataclass(frozen=True)
class FrameHash:
    """One perceptual hash: a whole image (no frame fields) or one video keyframe."""

    value: str
    frame_seq: int | None = None
    timestamp_seconds: float | None = None


@dataclass(frozen=True)
class LibraryEntry:
    artifact_id: str
    sha256: str
    media_type: str
    # Empty when the artifact has not been analysed (it then matches only byte-identically).
    hashes: tuple[FrameHash, ...] = ()


class LibraryReader:
    """Read access to the local artifact library, for duplicate search."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def snapshot(self, artifact_id: str, algorithm: str) -> "LibrarySnapshot":
        """Every other artifact in the duplicate library, and how many the analyst excluded (M2-7)."""
        stmt = (
            select(
                Artifact.id,
                Artifact.sha256,
                Artifact.media_type,
                Artifact.in_duplicate_library,
                ImageFingerprint.value_hex,
            )
            .outerjoin(
                ImageFingerprint,
                (ImageFingerprint.artifact_id == Artifact.id) & (ImageFingerprint.algorithm == algorithm),
            )
            .where(Artifact.id != artifact_id)
        )
        keyframes_stmt = (
            select(
                KeyframeFingerprint.artifact_id,
                KeyframeFingerprint.frame_seq,
                KeyframeFingerprint.timestamp_seconds,
                KeyframeFingerprint.value_hex,
            )
            .where(
                KeyframeFingerprint.algorithm == algorithm,
                KeyframeFingerprint.artifact_id != artifact_id,
            )
            .order_by(KeyframeFingerprint.artifact_id, KeyframeFingerprint.frame_seq)
        )
        with self._db.reader() as session:
            rows = session.execute(stmt).all()
            keyframe_rows = session.execute(keyframes_stmt).all()

        keyframes: dict[str, list[FrameHash]] = {}
        for owner, seq, timestamp, value in keyframe_rows:
            keyframes.setdefault(owner, []).append(FrameHash(value, seq, timestamp))

        entries, excluded = [], 0
        for owner, sha256, media_type, included, image_hash in rows:
            if not included:
                excluded += 1
                continue
            hashes: list[FrameHash] = []
            if image_hash is not None:
                hashes.append(FrameHash(image_hash))
            hashes.extend(keyframes.get(owner, []))
            entries.append(LibraryEntry(owner, sha256, media_type, tuple(hashes)))
        return LibrarySnapshot(entries=entries, excluded_count=excluded)


@dataclass(frozen=True)
class LibrarySnapshot:
    entries: list[LibraryEntry]
    # Artifacts left out because the analyst excluded them from duplicate search.
    excluded_count: int


@dataclass(frozen=True)
class FrameMatch:
    """A query hash paired with its best counterpart in the matched artifact, within the threshold."""

    distance: int
    similarity: float
    query_seq: int | None = None
    query_timestamp: float | None = None
    matched_seq: int | None = None
    matched_timestamp: float | None = None


@dataclass(frozen=True)
class DuplicateCandidate:
    """A match. Only the matched artifact's ID is kept, so deleting that artifact leaves no trace of
    its filename here; the evidence report looks the filename up when it is built."""

    artifact_id: str
    distance: int
    similarity: float
    match_type: MatchType
    # Frame detail (M3-4) when either side is a video: the best counterpart per query hash. Omitted
    # (None) for image-to-image and byte-identical matches, keeping the Milestone 1 shape.
    matched_frame_count: int | None = None
    frame_matches: list[FrameMatch] | None = field(default=None)


@dataclass(frozen=True)
class SearchResult:
    matches: list[DuplicateCandidate]
    library_size: int
    compared: int


def _similarity(distance: int) -> float:
    return round(1 - distance / BITS, 4)


def _match_entry(own: Sequence[FrameHash], entry: LibraryEntry, threshold: int) -> DuplicateCandidate | None:
    pairs: list[FrameMatch] = []
    for query in own:
        best: FrameMatch | None = None
        for candidate in entry.hashes:
            distance = hamming_distance(query.value, candidate.value)
            if distance <= threshold and (best is None or distance < best.distance):
                best = FrameMatch(
                    distance=distance,
                    similarity=_similarity(distance),
                    query_seq=query.frame_seq,
                    query_timestamp=query.timestamp_seconds,
                    matched_seq=candidate.frame_seq,
                    matched_timestamp=candidate.timestamp_seconds,
                )
        if best is not None:
            pairs.append(best)
    if not pairs:
        return None
    distance = min(pair.distance for pair in pairs)
    match_type: MatchType = "visually_identical" if distance == 0 else "near"
    plain_images = (
        len(own) == 1 and own[0].frame_seq is None and all(pair.matched_seq is None for pair in pairs)
    )
    if plain_images:
        return DuplicateCandidate(entry.artifact_id, distance, _similarity(distance), match_type)
    return DuplicateCandidate(
        entry.artifact_id,
        distance,
        _similarity(distance),
        match_type,
        matched_frame_count=len(pairs),
        frame_matches=pairs,
    )


def find_matches(
    sha256: str, own_hashes: Sequence[FrameHash], library: Iterable[LibraryEntry], threshold: int
) -> SearchResult:
    """Byte-identical files match by SHA-256; others match when any hash pair is within the threshold.

    For multi-frame artifacts, each of the query's hashes is paired with its best counterpart, so a
    matched artifact lists at most one pair per query frame.
    """
    matches: list[DuplicateCandidate] = []
    library_size = compared = 0
    for entry in library:
        library_size += 1
        if entry.sha256 == sha256:
            matches.append(DuplicateCandidate(entry.artifact_id, 0, 1.0, "exact_file"))
            continue
        if not entry.hashes:
            continue
        compared += 1
        match = _match_entry(own_hashes, entry, threshold)
        if match is not None:
            matches.append(match)
    matches.sort(key=lambda match: (match.distance, match.match_type != "exact_file", match.artifact_id))
    return SearchResult(matches, library_size, compared)
