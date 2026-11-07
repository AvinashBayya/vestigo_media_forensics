"""Milestone 3 follow-up (D19): the audio pipeline (`audio.v1`).

Audio is handled by the same machinery as video — the hashes, media-info, and metadata stages are
the existing classes bound to audio — plus a duplicates stage that is deliberately byte-identical
only: Vestigo performs no audio decoding, fingerprinting, transcription, or speaker identification
(M3-7 and the standing exclusions).
"""

from dataclasses import asdict

from app import __version__
from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageOutput
from app.pipeline.video_pipeline import (
    MediaInfoStage,
    VideoC2PAStage,
    VideoHashesStage,
    VideoLocationCluesStage,
    VideoMetadataStage,
    VideoStructuralStage,
)
from app.schemas.common import EvidenceClassification, MediaType
from app.services.duplicates import find_matches
from app.services.phash import FINGERPRINT_ALGORITHM

AUDIO_PIPELINE = "audio.v1"


class AudioHashesStage(VideoHashesStage):
    media_type = MediaType.AUDIO
    limitations = (
        "Hashes identify this exact sequence of bytes. Any re-encode, trim, remux, or metadata change "
        "produces different hashes, even when the audio sounds the same.",
        "MD5 is included for compatibility with other tools. It is not collision-resistant and should "
        "not be relied on alone.",
    )


class AudioMediaInfoStage(MediaInfoStage):
    media_type = MediaType.AUDIO


class AudioMetadataStage(VideoMetadataStage):
    media_type = MediaType.AUDIO


class AudioC2PAStage(VideoC2PAStage):
    media_type = MediaType.AUDIO


class AudioDuplicatesStage(AnalysisStage):
    name = "duplicates"
    media_type = MediaType.AUDIO
    method = (
        "Compares this file's SHA-256 with every other artifact in the local library. Only "
        "byte-identical files match: no audio is decoded, and no content-based audio comparison, "
        "fingerprinting, transcription, or speaker identification is performed. Artifacts the analyst "
        "excluded from duplicate search are not compared; their number is recorded."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original + local library"
    tool_name = "Vestigo duplicate search"
    option = "duplicate_search"
    limitations = (
        "Searches only the artifacts in this local Vestigo library, as it was when the job ran. No "
        "external or online search is performed.",
        "Only byte-identical copies are found. A re-encoded, trimmed, or re-tagged copy of the same "
        "recording will NOT match, because no content-based audio comparison is performed.",
        "Artifacts excluded from duplicate search by the analyst are not compared, even if identical. "
        "`excluded_count` records how many were left out.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return __version__

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        library = ctx.library.snapshot(artifact.id, FINGERPRINT_ALGORITHM)
        search = find_matches(artifact.sha256, [], library.entries, ctx.settings.phash_max_distance)
        return StageOutput(
            {
                "algorithm": "sha256",
                "threshold": None,
                "library_size": search.library_size,
                "compared": 0,
                "excluded_count": library.excluded_count,
                "matches": [asdict(match) for match in search.matches],
            }
        )


class AudioLocationCluesStage(VideoLocationCluesStage):
    """Metadata-derived clues only (M6): no audio is decoded and nothing is inferred from content."""

    media_type = MediaType.AUDIO


class AudioStructuralStage(VideoStructuralStage):
    """RIFF/container structure and byte statistics for audio (Pass 2). No audio is decoded."""

    media_type = MediaType.AUDIO


AUDIO_STAGES: tuple[AnalysisStage, ...] = (
    AudioHashesStage(),
    AudioMediaInfoStage(),
    AudioMetadataStage(),
    AudioC2PAStage(),
    AudioLocationCluesStage(),
    AudioStructuralStage(),
    AudioDuplicatesStage(),
)
