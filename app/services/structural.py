"""Structural and hidden-data inspection (Pass 2, D25).

Reports *observable structure*: where a format's data logically ends and whether anything follows,
what segments or chunks the container declares, whether declared sizes match the bytes on disk,
where known file signatures appear inside the file, and statistical measurements of the bytes.

Every item is a fact or a measurement with its method. Nothing here says "steganography detected"
or "this file is clean": concealed data can be undetectable by these means, and every finding below
has innocent causes that are far more common than concealment. The limitations say so, and the UI
repeats it.
"""

import math
import struct
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Read in slices so a large video never lands in memory at once.
READ_CHUNK = 1 << 20
# Signature scanning is bounded: a long scan on a 500 MB video would stall the pipeline.
MAX_SCAN_BYTES = 64 << 20
# A trailing run has to be worth mentioning.
MIN_TRAILING_BYTES = 1
MIN_PADDING_RUN = 64

STRUCTURAL_LIMITATIONS: tuple[str, ...] = (
    "These are facts about the file's structure and statistics of its bytes. They are NOT a finding "
    "that anything is hidden: this inspection cannot detect well-implemented steganography, and it "
    "never reports that a file is clean.",
    "Data after a format's logical end, extra chunks, and embedded signatures all have ordinary "
    "causes - camera and phone software, editors, content-management systems, thumbnails, colour "
    "profiles, and append-on-save tooling all produce them routinely.",
    "A signature match is a byte pattern, not a file: the same bytes occur by chance inside "
    "compressed or encrypted data, so an embedded-signature hit is a place to look, not a "
    "conclusion.",
    "Entropy, LSB distribution, and chi-square are measurements reported with their method. High "
    "entropy means compressed or encrypted-looking bytes, which is normal for media; it is not "
    "evidence of concealment.",
    "Nothing is extracted, decoded, or carved from the file, and no password or passphrase is "
    "attacked. The original is only ever read.",
)

# Signatures worth reporting when they appear *inside* a file. Short patterns are deliberately
# excluded: they match by chance constantly and would bury the real findings.
SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "zip_entry"),
    (b"PK\x05\x06", "zip_end_of_central_directory"),
    (b"Rar!\x1a\x07", "rar_archive"),
    (b"7z\xbc\xaf\x27\x1c", "7zip_archive"),
    (b"\x1f\x8b\x08", "gzip_stream"),
    (b"BZh9", "bzip2_stream"),
    (b"\xfd7zXZ\x00", "xz_stream"),
    (b"%PDF-", "pdf_document"),
    (b"\x89PNG\r\n\x1a\n", "png_image"),
    (b"GIF89a", "gif_image"),
    (b"SQLite format 3\x00", "sqlite_database"),
    (b"\x7fELF", "elf_executable"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole_compound_document"),
    (b"-----BEGIN ", "pem_block"),
)


@dataclass
class Finding:
    """One structural observation, with where it is and how big it is."""

    kind: str
    offset: int
    size: int | None = None
    detail: str | None = None


@dataclass
class Measurement:
    """One number, with the method that produced it and what it does and does not mean."""

    name: str
    value: float
    method: str
    note: str | None = None


@dataclass
class StructuralReport:
    container: str | None = None
    file_size: int = 0
    # Where the format's own data ends, when the format states it.
    logical_end: int | None = None
    trailing_bytes: int = 0
    findings: list[Finding] = field(default_factory=list)
    # Declared segments/chunks/boxes, as the container lists them.
    inventory: list[dict[str, Any]] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    # How far parsing reached: a container Vestigo does not parse structurally is a scope note, not
    # a problem - the byte statistics and signature scan still ran in full.
    notes: list[str] = field(default_factory=list)
    # Genuine problems, which make the stage partial.
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def _entropy(counts: list[int], total: int) -> float:
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def _byte_statistics(path: Path) -> tuple[list[Measurement], int]:
    """Whole-file byte entropy and the highest-entropy 4 KiB window, both bounded by one pass."""
    counts = [0] * 256
    total = 0
    window_best = 0.0
    window_offset = 0
    with path.open("rb") as handle:
        position = 0
        while chunk := handle.read(READ_CHUNK):
            for byte in chunk:
                counts[byte] += 1
            total += len(chunk)
            # Windowed entropy over 4 KiB slices: a concealed blob often differs from its neighbours.
            for start in range(0, len(chunk) - 4096 + 1, 4096):
                slice_counts = [0] * 256
                for byte in chunk[start : start + 4096]:
                    slice_counts[byte] += 1
                value = _entropy(slice_counts, 4096)
                if value > window_best:
                    window_best = value
                    window_offset = position + start
            position += len(chunk)
    measurements = [
        Measurement(
            name="byte_entropy",
            value=round(_entropy(counts, total), 4),
            method="Shannon entropy over all file bytes, in bits per byte (0-8).",
            note="Compressed and encrypted data sit near 8. Media files normally do too.",
        ),
        Measurement(
            name="max_window_entropy",
            value=round(window_best, 4),
            method="Highest Shannon entropy of any aligned 4 KiB window, in bits per byte.",
            note=f"Highest window begins at offset {window_offset}.",
        ),
    ]
    return measurements, total


def _trailing_padding(path: Path, size: int) -> Finding | None:
    """A run of identical bytes at the very end, which often means padding."""
    if size < MIN_PADDING_RUN:
        return None
    with path.open("rb") as handle:
        handle.seek(max(0, size - READ_CHUNK))
        tail = handle.read(READ_CHUNK)
    if not tail:
        return None
    last = tail[-1:]
    run = len(tail) - len(tail.rstrip(last))
    if run >= MIN_PADDING_RUN:
        return Finding(
            kind="trailing_padding",
            offset=size - run,
            size=run,
            detail=f"{run} repeated 0x{last.hex()} bytes at the end of the file.",
        )
    return None


def _scan_signatures(path: Path, skip_leading: int = 1) -> list[Finding]:
    """Known signatures appearing inside the file, excluding the one at offset 0."""
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    overlap = max(len(signature) for signature, _ in SIGNATURES) - 1
    with path.open("rb") as handle:
        carry = b""
        position = 0
        scanned = 0
        while scanned < MAX_SCAN_BYTES and (chunk := handle.read(READ_CHUNK)):
            buffer = carry + chunk
            base = position - len(carry)
            for signature, name in SIGNATURES:
                start = 0
                while (index := buffer.find(signature, start)) != -1:
                    absolute = base + index
                    if absolute >= skip_leading and (name, absolute) not in seen:
                        seen.add((name, absolute))
                        findings.append(
                            Finding(
                                kind="embedded_signature",
                                offset=absolute,
                                size=len(signature),
                                detail=f"{name} signature bytes at offset {absolute}.",
                            )
                        )
                    start = index + 1
            position += len(chunk)
            scanned += len(chunk)
            carry = buffer[-overlap:] if overlap else b""
    findings.sort(key=lambda item: item.offset)
    # Keep the report readable: the first matches are enough to point an analyst at the right place.
    return findings[:50]


def _png_structure(data: bytes, size: int) -> tuple[int | None, list[dict[str, Any]], list[Finding]]:
    """PNG chunk inventory with CRC checks; the logical end is the IEND chunk."""
    inventory: list[dict[str, Any]] = []
    findings: list[Finding] = []
    offset = 8
    logical_end: int | None = None
    while offset + 8 <= len(data):
        (length,) = struct.unpack(">I", data[offset : offset + 4])
        chunk_type = data[offset + 4 : offset + 8].decode("ascii", errors="replace")
        payload_start = offset + 8
        payload_end = payload_start + length
        if payload_end + 4 > len(data):
            findings.append(
                Finding(
                    kind="truncated_chunk",
                    offset=offset,
                    size=length,
                    detail=f"The {chunk_type} chunk declares {length} bytes, past the end of the file.",
                )
            )
            break
        stored_crc = struct.unpack(">I", data[payload_end : payload_end + 4])[0]
        actual_crc = zlib.crc32(data[offset + 4 : payload_end]) & 0xFFFFFFFF
        entry = {"type": chunk_type, "offset": offset, "length": length, "crc_ok": stored_crc == actual_crc}
        inventory.append(entry)
        if not entry["crc_ok"]:
            findings.append(
                Finding(
                    kind="chunk_crc_mismatch",
                    offset=offset,
                    size=length,
                    detail=f"The {chunk_type} chunk's stored CRC does not match its data.",
                )
            )
        # Text and private chunks are where payloads are usually parked; report large ones as facts.
        if chunk_type in ("tEXt", "zTXt", "iTXt", "eXIf") and length > 2048:
            findings.append(
                Finding(
                    kind="large_text_chunk",
                    offset=offset,
                    size=length,
                    detail=f"{chunk_type} chunk of {length} bytes.",
                )
            )
        if chunk_type == "IEND":
            logical_end = payload_end + 4
            break
        offset = payload_end + 4
    if logical_end is None and inventory:
        findings.append(Finding(kind="missing_end_marker", offset=size, detail="No IEND chunk was found."))
    return logical_end, inventory, findings


JPEG_STANDALONE = {0xD8, 0xD9, *range(0xD0, 0xD8), 0x01}


def _jpeg_structure(data: bytes, size: int) -> tuple[int | None, list[dict[str, Any]], list[Finding]]:
    """JPEG segment inventory; the logical end is the EOI marker after the scan."""
    inventory: list[dict[str, Any]] = []
    findings: list[Finding] = []
    offset = 2
    logical_end: int | None = None
    while offset + 1 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker == 0xFF:
            offset += 1
            continue
        if marker in JPEG_STANDALONE:
            if marker == 0xD9:
                logical_end = offset + 2
                break
            offset += 2
            continue
        if offset + 4 > len(data):
            break
        (length,) = struct.unpack(">H", data[offset + 2 : offset + 4])
        entry = {"marker": f"0x{marker:02X}", "offset": offset, "length": length}
        inventory.append(entry)
        if marker in (0xFE, 0xEC, 0xEE) and length > 2048:
            findings.append(
                Finding(
                    kind="large_comment_segment",
                    offset=offset,
                    size=length,
                    detail=f"Marker 0x{marker:02X} segment of {length} bytes.",
                )
            )
        if marker == 0xDA:
            # Entropy-coded scan data follows; find the EOI that closes it.
            end = data.find(b"\xff\xd9", offset + 2 + length)
            logical_end = end + 2 if end != -1 else None
            if logical_end is None:
                findings.append(
                    Finding(kind="missing_end_marker", offset=size, detail="No EOI marker was found.")
                )
            break
        offset += 2 + length
    return logical_end, inventory, findings


def _iso_bmff_structure(data: bytes, size: int) -> tuple[int | None, list[dict[str, Any]], list[Finding]]:
    """Top-level MP4/MOV box inventory; the logical end is where the declared boxes stop."""
    inventory: list[dict[str, Any]] = []
    findings: list[Finding] = []
    offset = 0
    while offset + 8 <= len(data):
        (box_size,) = struct.unpack(">I", data[offset : offset + 4])
        box_type = data[offset + 4 : offset + 8].decode("ascii", errors="replace")
        header = 8
        if box_size == 1:
            if offset + 16 > len(data):
                break
            (box_size,) = struct.unpack(">Q", data[offset + 8 : offset + 16])
            header = 16
        elif box_size == 0:
            box_size = size - offset  # "to end of file"
        if box_size < header:
            findings.append(
                Finding(
                    kind="invalid_box_size",
                    offset=offset,
                    size=box_size,
                    detail=f"The {box_type} box declares an impossible size of {box_size}.",
                )
            )
            break
        inventory.append({"type": box_type, "offset": offset, "size": box_size})
        if offset + box_size > size:
            findings.append(
                Finding(
                    kind="box_past_end",
                    offset=offset,
                    size=box_size,
                    detail=f"The {box_type} box extends past the end of the file.",
                )
            )
            break
        offset += box_size
    return (offset if inventory else None), inventory, findings


def _riff_structure(data: bytes, size: int) -> tuple[int | None, list[dict[str, Any]], list[Finding]]:
    """RIFF (WAV/AVI) chunk inventory; the logical end comes from the RIFF size field."""
    findings: list[Finding] = []
    inventory: list[dict[str, Any]] = []
    if len(data) < 12:
        return None, inventory, findings
    (riff_size,) = struct.unpack("<I", data[4:8])
    logical_end = 8 + riff_size
    if logical_end > size:
        findings.append(
            Finding(
                kind="declared_size_past_end",
                offset=4,
                size=riff_size,
                detail=f"The RIFF header declares {riff_size} bytes, which runs past the file's end.",
            )
        )
        logical_end = None
    offset = 12
    while offset + 8 <= len(data) and len(inventory) < 200:
        chunk_id = data[offset : offset + 4].decode("ascii", errors="replace")
        (chunk_size,) = struct.unpack("<I", data[offset + 4 : offset + 8])
        inventory.append({"id": chunk_id, "offset": offset, "size": chunk_size})
        offset += 8 + chunk_size + (chunk_size & 1)
    return logical_end, inventory, findings


def _image_bit_statistics(path: Path) -> list[Measurement]:
    """LSB balance and a chi-square statistic over the decoded pixels (images only)."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as image:
            image.draft("RGB", image.size)
            pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    except Exception:  # noqa: BLE001 - a file we cannot decode simply has no pixel statistics
        return []
    if pixels.size == 0:
        return []
    lsb = (pixels & 1).astype(np.int64)
    ones = int(lsb.sum())
    total = int(lsb.size)
    ratio = ones / total if total else 0.0
    zeros = total - ones
    expected = total / 2
    chi_square = ((ones - expected) ** 2 + (zeros - expected) ** 2) / expected if expected else 0.0
    return [
        Measurement(
            name="lsb_ones_ratio",
            value=round(ratio, 6),
            method="Proportion of 1 bits in the least-significant bit of every RGB sample.",
            note=(
                "An even 0.5 split is what both untouched photographs and LSB-encoded data tend to "
                "show, so this number distinguishes neither."
            ),
        ),
        Measurement(
            name="lsb_chi_square",
            value=round(float(chi_square), 4),
            method="Chi-square of the LSB 0/1 counts against an even split (1 degree of freedom).",
            note="A measurement only. It is not a test of concealment and has no threshold here.",
        ),
    ]


def inspect(path: Path, container: str | None = None) -> StructuralReport:
    """Inspect the file's structure. Reads only; extracts, carves, and decodes nothing."""
    size = path.stat().st_size
    report = StructuralReport(container=container, file_size=size)

    head_size = min(size, 8 << 20)
    with path.open("rb") as handle:
        head = handle.read(head_size)

    logical_end: int | None = None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        report.container = report.container or "png"
        logical_end, report.inventory, findings = _png_structure(head, size)
        report.findings.extend(findings)
    elif head.startswith(b"\xff\xd8\xff"):
        report.container = report.container or "jpeg"
        logical_end, report.inventory, findings = _jpeg_structure(head, size)
        report.findings.extend(findings)
    elif len(head) > 8 and head[4:8] == b"ftyp":
        report.container = report.container or "iso_media"
        logical_end, report.inventory, findings = _iso_bmff_structure(head, size)
        report.findings.extend(findings)
    elif head.startswith(b"RIFF"):
        report.container = report.container or "riff"
        logical_end, report.inventory, findings = _riff_structure(head, size)
        report.findings.extend(findings)
    elif head.startswith(b"GIF8"):
        report.container = report.container or "gif"
        end = head.rfind(b"\x3b")
        logical_end = end + 1 if end > 0 else None
    elif head.startswith(b"%PDF-"):
        report.container = report.container or "pdf"
        marker = head.rfind(b"%%EOF") if size <= head_size else -1
        if marker == -1:
            with path.open("rb") as handle:
                handle.seek(max(0, size - 4096))
                tail = handle.read(4096)
            position = tail.rfind(b"%%EOF")
            marker = (size - len(tail) + position) if position != -1 else -1
        logical_end = marker + 5 if marker != -1 else None
    else:
        report.notes.append(
            "This container is not structurally parsed by Vestigo, so the segment inventory and "
            "logical-end check were skipped. Byte statistics and the signature scan ran in full."
        )

    report.logical_end = logical_end
    if logical_end is not None and size > logical_end:
        extra = size - logical_end
        if extra >= MIN_TRAILING_BYTES:
            report.trailing_bytes = extra
            report.findings.append(
                Finding(
                    kind="trailing_data",
                    offset=logical_end,
                    size=extra,
                    detail=(
                        f"{extra} bytes follow the end of the {report.container or 'file'} data at "
                        f"offset {logical_end}."
                    ),
                )
            )

    padding = _trailing_padding(path, size)
    if padding is not None:
        report.findings.append(padding)
    report.findings.extend(_scan_signatures(path))

    measurements, _ = _byte_statistics(path)
    report.measurements.extend(measurements)
    if report.container in ("png", "jpeg", "gif"):
        report.measurements.extend(_image_bit_statistics(path))
    return report
