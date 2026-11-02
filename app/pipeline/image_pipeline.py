"""Milestone 1 image pipeline (`image.v1`). Stages run in the order of IMAGE_STAGES."""

from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageFailure, StageOutput
from app.schemas.common import EvidenceClassification, MediaType
from app.services.hashing import hash_file, hashlib_version

IMAGE_PIPELINE = "image.v1"


class HashesStage(AnalysisStage):
    name = "hashes"
    media_type = MediaType.IMAGE
    method = (
        "SHA-256 and MD5 computed over the stored original's bytes and compared with the values "
        "recorded when the file was uploaded."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "hashlib"
    limitations = (
        "Hashes identify this exact sequence of bytes. Any re-save, crop, or metadata change produces "
        "different hashes, even when the image looks the same.",
        "MD5 is included for compatibility with other tools. It is not collision-resistant and should "
        "not be relied on alone.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        return hashlib_version()

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        hashes = hash_file(artifact.path)
        matches = (hashes.sha256, hashes.md5, hashes.size_bytes) == (
            artifact.sha256,
            artifact.md5,
            artifact.size_bytes,
        )
        data = {
            "sha256": hashes.sha256,
            "md5": hashes.md5,
            "size_bytes": hashes.size_bytes,
            "matches_upload_record": matches,
        }
        if not matches:
            raise StageFailure(
                "INTEGRITY_MISMATCH",
                "The stored file no longer matches the hashes recorded at upload.",
                data,
            )
        return StageOutput(data)


IMAGE_STAGES: tuple[AnalysisStage, ...] = (HashesStage(),)
