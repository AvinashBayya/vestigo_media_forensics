"""PDF structure, text, and embedded images (Pass 2, D25).

Parsed in pure Python: no PDF library is used, so what Vestigo reports is what the bytes say. The
structure half is OBSERVED fact - the header version, object and page counts, incremental updates,
encryption, signature and form dictionaries, and the presence of embedded files, JavaScript, and
automatic actions. Extracted text is DERIVED and **provisional**, the same honesty rule as OCR
(D14): it comes from content-stream operators without font mapping, so characters can be wrong or
missing, and it is never a verified transcription.

Signature *presence* is a structural fact. Vestigo does not validate PDF signatures and never says a
document is signed-and-trusted; a /Sig dictionary means the file contains one, nothing more.
"""

import re
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Bounds, so a hostile or enormous PDF cannot stall the pipeline.
MAX_PARSE_BYTES = 64 << 20
MAX_STREAMS = 400
MAX_EMBEDDED_IMAGES = 40
MAX_TEXT_CHARACTERS = 400_000

PDF_STRUCTURE_LIMITATIONS: tuple[str, ...] = (
    "Structure is read from the file's bytes without a PDF library, so counts are of what the file "
    "declares. A malformed or deliberately confusing document can declare one thing and render "
    "another.",
    "The presence of JavaScript, an automatic action, an embedded file, or a form is a structural "
    "fact, not a finding of wrongdoing: ordinary documents from ordinary software contain all of "
    "these routinely.",
    "A signature dictionary means the file contains a signature structure. Vestigo does NOT "
    "validate PDF signatures, check certificates, or establish signer trust, and never reports a "
    "document as signed and valid.",
    "Incremental updates are how PDFs are normally saved and annotated. Several of them mean the "
    "file was saved more than once, not that it was tampered with.",
    "Encryption is reported when the file declares it. Vestigo does not attempt to decrypt, and no "
    "password is ever attacked.",
)

PDF_TEXT_LIMITATIONS: tuple[str, ...] = (
    "Provisional, best-effort text, not a verified transcription. It is read from content-stream "
    "operators without font or encoding mapping, so characters can be wrong, reordered, or missing "
    "entirely - especially for embedded, subset, or non-Latin fonts.",
    "Text drawn as an image is not extracted here at all. Run OCR over the extracted images for "
    "that, and treat its output as provisional too (D14).",
    "Reading order follows the order operators appear in the file, which is not always the reading "
    "order a person sees on the page.",
    "An empty result does not mean the page has no text.",
)

PDF_IMAGE_LIMITATIONS: tuple[str, ...] = (
    "Only JPEG-compressed (DCTDecode) embedded images are extracted, byte for byte as they are "
    "stored. Images in other encodings are counted but not extracted, because rebuilding them "
    "would mean re-encoding, and a re-encoded image is not the stored evidence.",
    "These are images embedded in the document, not rendered pages: Vestigo has no PDF renderer, so "
    "page appearance is not reproduced.",
    "An extracted image is a copy of the stored stream. The original document is never modified.",
)

_OBJECT = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
_PAGE = re.compile(rb"/Type\s*/Page\b(?![s])")
_STREAM = re.compile(rb"stream\r?\n?", re.IGNORECASE)
_HEADER = re.compile(rb"%PDF-(\d+\.\d+)")
_TEXT_SHOW = re.compile(rb"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\]\\]|\\.)*\]\s*TJ", re.DOTALL)
_STRING = re.compile(rb"\((?:\\.|[^\\()])*\)", re.DOTALL)

# Structural markers worth reporting, each a fact about what the file contains.
MARKERS: tuple[tuple[bytes, str], ...] = (
    (b"/Encrypt", "encryption_dictionary"),
    (b"/JavaScript", "javascript"),
    (b"/JS", "javascript_action"),
    (b"/OpenAction", "open_action"),
    (b"/AA", "additional_actions"),
    (b"/Launch", "launch_action"),
    (b"/EmbeddedFile", "embedded_file"),
    (b"/Filespec", "file_specification"),
    (b"/AcroForm", "interactive_form"),
    (b"/XFA", "xfa_form"),
    (b"/ByteRange", "signature_byte_range"),
    (b"/ObjStm", "object_stream"),
    (b"/URI", "uri_action"),
)


@dataclass
class PdfStructure:
    pdf_version: str | None = None
    file_size: int = 0
    object_count: int = 0
    page_count: int = 0
    # Each %%EOF marks a save; more than one means the file was updated incrementally.
    eof_markers: int = 0
    startxref_markers: int = 0
    incremental_updates: int = 0
    encrypted: bool = False
    # Structural presence only: {"javascript": 2, ...}
    markers: dict[str, int] = field(default_factory=dict)
    # Signature dictionaries found, as a count. Never validated.
    signature_count: int = 0
    linearized: bool = False
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PdfText:
    text: str = ""
    character_count: int = 0
    streams_read: int = 0
    # Streams that are not text streams at all (images, binary data).
    streams_skipped: int = 0
    streams_failed: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EmbeddedImage:
    index: int
    encoding: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    data: bytes | None = None


def read_structure(path: Path) -> PdfStructure:
    """Structural facts about the document, read from its bytes."""
    size = path.stat().st_size
    structure = PdfStructure(file_size=size)
    with path.open("rb") as handle:
        data = handle.read(MAX_PARSE_BYTES)
    if size > len(data):
        structure.notes.append(f"Only the first {len(data)} bytes were parsed; the file is {size} bytes.")

    header = _HEADER.search(data[:1024])
    structure.pdf_version = header.group(1).decode("ascii") if header else None
    if header is None:
        structure.warnings.append("No %PDF- header was found in the first kilobyte.")

    structure.object_count = len(set(_OBJECT.findall(data)))
    structure.page_count = len(_PAGE.findall(data))
    structure.eof_markers = data.count(b"%%EOF")
    structure.startxref_markers = data.count(b"startxref")
    structure.incremental_updates = max(0, structure.eof_markers - 1)
    structure.linearized = b"/Linearized" in data[:4096]

    for marker, name in MARKERS:
        count = data.count(marker)
        if count:
            structure.markers[name] = count
    structure.encrypted = "encryption_dictionary" in structure.markers
    structure.signature_count = len(re.findall(rb"/Type\s*/Sig\b", data))

    if structure.page_count == 0:
        structure.notes.append(
            "No /Type /Page objects were visible. Pages may live in compressed object streams, "
            "which Vestigo does not expand."
        )
    if structure.encrypted:
        structure.notes.append(
            "The document declares encryption. Text and image extraction will usually return "
            "nothing, and Vestigo does not attempt to decrypt."
        )
    return structure


def _decode_pdf_string(raw: bytes) -> str:
    """One literal PDF string, with the escapes that matter for reading text."""
    body = raw[1:-1]
    out = bytearray()
    index = 0
    while index < len(body):
        byte = body[index]
        if byte == 0x5C and index + 1 < len(body):  # backslash
            nxt = body[index + 1]
            mapping = {0x6E: 0x0A, 0x72: 0x0D, 0x74: 0x09, 0x62: 0x08, 0x66: 0x0C}
            if nxt in mapping:
                out.append(mapping[nxt])
                index += 2
                continue
            if 0x30 <= nxt <= 0x37:  # octal escape
                digits = body[index + 1 : index + 4]
                octal = bytes(d for d in digits if 0x30 <= d <= 0x37)
                out.append(int(octal.decode("ascii"), 8) & 0xFF)
                index += 1 + len(octal)
                continue
            out.append(nxt)
            index += 2
            continue
        out.append(byte)
        index += 1
    return out.decode("latin-1", errors="replace")


def _strip_stream_eol(payload: bytes) -> bytes:
    """Drop the single end-of-line that may precede `endstream`; it is not part of the data."""
    if payload.endswith(b"\r\n"):
        return payload[:-2]
    if payload.endswith((b"\n", b"\r")):
        return payload[:-1]
    return payload


def _streams(data: bytes) -> list[bytes]:
    """Raw stream payloads, bounded in number."""
    payloads: list[bytes] = []
    for match in _STREAM.finditer(data):
        start = match.end()
        end = data.find(b"endstream", start)
        if end == -1:
            break
        payloads.append(_strip_stream_eol(data[start:end]))
        if len(payloads) >= MAX_STREAMS:
            break
    return payloads


def extract_text(path: Path) -> PdfText:
    """Best-effort text from content streams. Provisional by construction (D14 precedent)."""
    result = PdfText()
    with path.open("rb") as handle:
        data = handle.read(MAX_PARSE_BYTES)

    pieces: list[str] = []
    for payload in _streams(data):
        content = payload
        if payload[:2] in (b"\x78\x9c", b"\x78\x01", b"\x78\xda", b"\x78\x5e"):
            try:
                content = zlib.decompress(payload)
            except zlib.error:
                try:
                    content = zlib.decompressobj().decompress(payload)
                except zlib.error:
                    # It announced itself as zlib and still would not decompress: a real problem.
                    result.streams_failed += 1
                    continue
        elif b"Tj" not in payload and b"TJ" not in payload:
            # An image or other binary stream is not a text stream; skipping it is not a failure.
            result.streams_skipped += 1
            continue
        if b"Tj" not in content and b"TJ" not in content:
            continue
        result.streams_read += 1
        for show in _TEXT_SHOW.finditer(content):
            chunk = show.group(0)
            for string in _STRING.finditer(chunk):
                pieces.append(_decode_pdf_string(string.group(0)))
            if chunk.rstrip().endswith(b"Tj"):
                pieces.append(" ")
            else:
                pieces.append(" ")
        pieces.append("\n")

    text = "".join(pieces)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    result.text = text[:MAX_TEXT_CHARACTERS]
    result.character_count = len(result.text)
    if not result.text:
        result.notes.append(
            "No text operators were readable. The document may be image-only, encrypted, or use "
            "compressed object streams Vestigo does not expand. This does not mean the pages are "
            "blank."
        )
    if result.streams_failed:
        result.notes.append(
            f"{result.streams_failed} compressed stream(s) could not be decompressed and were skipped."
        )
    return result


def extract_images(path: Path) -> tuple[list[EmbeddedImage], list[str]]:
    """JPEG-compressed embedded images, byte for byte. Other encodings are counted only."""
    notes: list[str] = []
    with path.open("rb") as handle:
        data = handle.read(MAX_PARSE_BYTES)

    images: list[EmbeddedImage] = []
    other_encodings = 0
    index = 0
    position = 0
    while (marker := data.find(b"/Subtype", position)) != -1:
        position = marker + 8
        window = data[marker : marker + 600]
        if b"/Image" not in window:
            continue
        stream = data.find(b"stream", marker)
        if stream == -1:
            continue
        end = data.find(b"endstream", stream)
        if end == -1:
            continue
        payload_start = stream + 6
        while payload_start < len(data) and data[payload_start] in (0x0D, 0x0A):
            payload_start += 1
        payload = _strip_stream_eol(data[payload_start:end])
        width = height = None
        if (found := re.search(rb"/Width\s+(\d+)", window)) is not None:
            width = int(found.group(1))
        if (found := re.search(rb"/Height\s+(\d+)", window)) is not None:
            height = int(found.group(1))

        if b"DCTDecode" in window and payload[:3] == b"\xff\xd8\xff":
            if len(images) < MAX_EMBEDDED_IMAGES:
                index += 1
                images.append(
                    EmbeddedImage(
                        index=index,
                        encoding="DCTDecode",
                        size_bytes=len(payload),
                        width=width,
                        height=height,
                        data=payload,
                    )
                )
        else:
            other_encodings += 1
        position = end
    if other_encodings:
        notes.append(
            f"{other_encodings} embedded image(s) use an encoding other than JPEG and were counted "
            "but not extracted: rebuilding them would mean re-encoding, and a re-encoded image is "
            "not the stored evidence."
        )
    return images, notes
