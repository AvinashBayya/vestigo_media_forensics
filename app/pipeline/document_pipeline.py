"""The document pipeline (document.v1, Pass 2, D25).

Hashes and metadata reuse the image pipeline's stages unchanged. On top of them:

- `pdf_structure` reads structural facts from the bytes: version, object and page counts,
  incremental updates, encryption, signature *presence*, and whether the file contains JavaScript,
  automatic actions, embedded files, or forms. OBSERVED; nothing is validated or executed.
- `pdf_text` extracts provisional text from content streams (DERIVED, labelled like OCR under D14).
- `pdf_images` copies JPEG-compressed embedded images out byte for byte as derived files, with
  per-image lineage, so OCR and the analyst can work on real stored bytes rather than a re-encode.
- `structural` and `duplicates` are the shared stages; audio and video stages do not apply.

A PDF is only ever read. Nothing in it is rendered, executed, decrypted, or attacked.
"""

from dataclasses import asdict

from app.pipeline.base import AnalysisStage, ArtifactView, StageContext, StageOutput
from app.pipeline.image_pipeline import HashesStage, MetadataStage, StructuralStage
from app.schemas.common import EvidenceClassification, MediaType
from app.schemas.evidence import StageError
from app.services.duplicates import find_matches
from app.services.pdf import (
    PDF_IMAGE_LIMITATIONS,
    PDF_STRUCTURE_LIMITATIONS,
    PDF_TEXT_LIMITATIONS,
    extract_images,
    extract_text,
    read_structure,
)
from app.services.phash import FINGERPRINT_ALGORITHM

DOCUMENT_PIPELINE = "document.v1"


class DocumentHashesStage(HashesStage):
    media_type = MediaType.DOCUMENT


class DocumentMetadataStage(MetadataStage):
    media_type = MediaType.DOCUMENT


class DocumentStructuralStage(StructuralStage):
    media_type = MediaType.DOCUMENT


class PdfStructureStage(AnalysisStage):
    name = "pdf_structure"
    media_type = MediaType.DOCUMENT
    method = (
        "The PDF is parsed in place in pure Python, with no PDF library: the header version, the "
        "number of distinct indirect objects and /Type /Page objects, %%EOF and startxref markers "
        "(so incremental saves are visible), whether the file declares encryption or linearisation, "
        "how many signature dictionaries it contains, and which structural features are present - "
        "JavaScript, automatic actions, embedded files, file specifications, forms, object streams, "
        "and URI actions - each as a count. Nothing is rendered, executed, or decrypted."
    )
    classification = EvidenceClassification.OBSERVED
    source = "artifact:original"
    tool_name = "vestigo-pdf"
    option = "pdf_structure"
    limitations = PDF_STRUCTURE_LIMITATIONS

    def tool_version(self, ctx: StageContext) -> str:
        from app import __version__

        return f"Vestigo {__version__}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        structure = read_structure(artifact.path)
        warnings = [
            StageError(type="PDF_STRUCTURE_PROBLEM", message=message) for message in structure.warnings
        ]
        return StageOutput(data=structure.as_dict(), warnings=warnings)


class PdfTextStage(AnalysisStage):
    name = "pdf_text"
    media_type = MediaType.DOCUMENT
    method = (
        "Text-showing operators (Tj and TJ) are read from the document's content streams, "
        "decompressing FlateDecode streams with zlib. No font, encoding, or ToUnicode mapping is "
        "applied, so this is provisional text in the order the operators appear - not a verified "
        "transcription and not necessarily the reading order on the page."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "vestigo-pdf"
    option = "pdf_text"
    limitations = PDF_TEXT_LIMITATIONS

    def tool_version(self, ctx: StageContext) -> str:
        from app import __version__

        return f"Vestigo {__version__}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        result = extract_text(artifact.path)
        if result.text:
            ctx.derived.write(self.name, "pdf_text", "text.txt", result.text.encode("utf-8"))
        return StageOutput(data=result.as_dict())


class PdfImagesStage(AnalysisStage):
    name = "pdf_images"
    media_type = MediaType.DOCUMENT
    method = (
        "Embedded image XObjects are located in the document's bytes. JPEG-compressed (DCTDecode) "
        "images are copied out byte for byte as derived files, each recording the document as its "
        "source; images in other encodings are counted but not extracted, because rebuilding them "
        "would require re-encoding. These are images embedded in the file, not rendered pages."
    )
    classification = EvidenceClassification.OBSERVED
    source = "artifact:original"
    tool_name = "vestigo-pdf"
    option = "pdf_images"
    limitations = PDF_IMAGE_LIMITATIONS

    def tool_version(self, ctx: StageContext) -> str:
        from app import __version__

        return f"Vestigo {__version__}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        images, notes = extract_images(artifact.path)
        extracted = []
        for image in images:
            info = ctx.derived.write(
                self.name,
                "pdf_embedded_image",
                f"{image.index:04d}.jpg",
                image.data or b"",
            )
            extracted.append(
                {
                    "index": image.index,
                    "encoding": image.encoding,
                    "size_bytes": image.size_bytes,
                    "width": image.width,
                    "height": image.height,
                    "derived_file_id": info.derived_file_id,
                }
            )
        return StageOutput(data={"images": extracted, "extracted": len(extracted), "notes": notes})


class DocumentDuplicatesStage(AnalysisStage):
    name = "duplicates"
    media_type = MediaType.DOCUMENT
    method = (
        "The document's SHA-256 is compared with every other artifact in the local library. Only "
        "byte-identical files match: Vestigo does not compare document text or layout, so a "
        "re-saved or re-exported copy of the same document will not match."
    )
    classification = EvidenceClassification.DERIVED
    source = "artifact:original"
    tool_name = "vestigo-duplicates"
    option = "duplicate_search"
    limitations = (
        "Matching is byte-identical only. A re-saved, re-exported, or annotated copy of the same "
        "document has different bytes and will not match.",
        "Only artifacts in this local library are compared, as the library stood when this analysis "
        "ran, and artifacts the analyst excluded are skipped.",
        "A byte-identical match means the same file is held twice. It says nothing about which copy "
        "came first or where either came from.",
    )

    def tool_version(self, ctx: StageContext) -> str:
        from app import __version__

        return f"Vestigo {__version__}"

    def analyze(self, artifact: ArtifactView, ctx: StageContext) -> StageOutput:
        library = ctx.library.snapshot(artifact.id, FINGERPRINT_ALGORITHM)
        search = find_matches(artifact.sha256, [], library.entries, ctx.settings.phash_max_distance)
        return StageOutput(
            data={
                "algorithm": "sha256",
                "threshold": None,
                "library_size": search.library_size,
                "compared": 0,
                "excluded_count": library.excluded_count,
                "matches": [asdict(match) for match in search.matches],
            }
        )


DOCUMENT_STAGES: tuple[AnalysisStage, ...] = (
    DocumentHashesStage(),
    DocumentMetadataStage(),
    PdfStructureStage(),
    PdfTextStage(),
    PdfImagesStage(),
    DocumentStructuralStage(),
    DocumentDuplicatesStage(),
)
