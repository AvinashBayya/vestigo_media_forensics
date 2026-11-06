"""C2PA / Content Credentials detection.

Detection only. Two independent checks look for an embedded C2PA manifest store:

- a byte-level scan of the container (JPEG APP11, PNG caBX chunk, WebP C2PA chunk, TIFF tag 52545)
  for a JUMBF box whose type is "c2pa";
- ExifTool, which decodes the JUMBF boxes and the CBOR/JSON inside them.

Nothing here verifies signatures, certificates, or hash bindings. Validation is planned for
Milestone 4 (06-ROADMAP.md).
"""

import json as _json
import re
import struct
from dataclasses import dataclass, field
from importlib.metadata import version as _dist_version
from pathlib import Path
from typing import Any, Literal

import c2pa as _c2pa

from app.core.tools import ToolStatus
from app.services.metadata import run_exiftool_json

EXIFTOOL_ARGS = (
    "-json",
    "-G3:1",
    "-a",
    "-struct",
    "-JUMBF:all",
    "-XMP-dcterms:Provenance",
    "-Warning",
    "-Error",
)
C2PA_TIFF_TAG = 0xCD41
_C2PA_TYPE_PREFIX = b"c2pa"
_DOC_ID = re.compile(r"Doc\d+(?:-\d+)*")


# --- Byte-level scan -------------------------------------------------------------------------


@dataclass
class ByteScan:
    found: bool = False
    container: str | None = None
    segments: int = 0
    total_bytes: int = 0
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "container": self.container,
            "segments": self.segments,
            "bytes": self.total_bytes,
        }


def _jumbf_is_c2pa_store(box: bytes) -> bool:
    """True if `box` starts with a JUMBF superbox whose description box has the C2PA type."""
    if len(box) < 8 or box[4:8] != b"jumb":
        return False
    offset = 16 if struct.unpack(">I", box[:4])[0] == 1 else 8  # XLBox present when LBox == 1
    description = box[offset:]
    return len(description) >= 12 and description[4:8] == b"jumd" and description[8:12] == _C2PA_TYPE_PREFIX


def _scan_jpeg(data: bytes, scan: ByteScan) -> None:
    scan.container = "jpeg_app11"
    c2pa_instances: set[int] = set()
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            scan.problems.append("JPEG marker structure is malformed before the image data.")
            return
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            pos += 2
            continue
        if marker in (0xDA, 0xD9):  # start of scan / end of image: no metadata segments follow
            return
        length = struct.unpack(">H", data[pos + 2 : pos + 4])[0]
        if length < 2 or pos + 2 + length > len(data):
            scan.problems.append("A JPEG segment is truncated.")
            return
        payload = data[pos + 4 : pos + 2 + length]
        if marker == 0xEB and payload[:2] == b"JP" and len(payload) >= 8:
            instance, sequence = struct.unpack(">HI", payload[2:8])
            if sequence == 1 and _jumbf_is_c2pa_store(payload[8:]):
                c2pa_instances.add(instance)
            if instance in c2pa_instances:
                scan.found = True
                scan.segments += 1
                scan.total_bytes += len(payload) - 8
        pos += 2 + length


def _scan_png(data: bytes, scan: ByteScan) -> None:
    scan.container = "png_caBX"
    pos = 8
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        kind = data[pos + 4 : pos + 8]
        if pos + 12 + length > len(data):
            scan.problems.append("A PNG chunk is truncated.")
            return
        if kind == b"caBX":
            scan.segments += 1
            scan.total_bytes += length
            if _jumbf_is_c2pa_store(data[pos + 8 : pos + 8 + length]):
                scan.found = True
            else:
                scan.problems.append("A caBX chunk does not start with a C2PA JUMBF box.")
        if kind == b"IEND":
            return
        pos += 12 + length


def _scan_webp(data: bytes, scan: ByteScan) -> None:
    scan.container = "webp_C2PA"
    pos = 12
    while pos + 8 <= len(data):
        kind = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        if pos + 8 + size > len(data):
            scan.problems.append("A WebP chunk is truncated.")
            return
        if kind == b"C2PA":
            scan.segments += 1
            scan.total_bytes += size
            if _jumbf_is_c2pa_store(data[pos + 8 : pos + 8 + size]):
                scan.found = True
            else:
                scan.problems.append("A C2PA chunk does not start with a C2PA JUMBF box.")
        pos += 8 + size + (size % 2)


def _scan_tiff(data: bytes, scan: ByteScan) -> None:
    scan.container = "tiff_tag_52545"
    endian = "<" if data[:2] == b"II" else ">"
    try:
        (ifd_offset,) = struct.unpack(endian + "I", data[4:8])
        (count,) = struct.unpack(endian + "H", data[ifd_offset : ifd_offset + 2])
        for index in range(count):
            entry = ifd_offset + 2 + index * 12
            tag, _type, length, value_offset = struct.unpack(endian + "HHII", data[entry : entry + 12])
            if tag == C2PA_TIFF_TAG:
                scan.segments += 1
                scan.total_bytes += length
                scan.found = _jumbf_is_c2pa_store(data[value_offset : value_offset + length])
                if not scan.found:
                    scan.problems.append("TIFF tag 52545 does not contain a C2PA JUMBF box.")
    except struct.error:
        scan.problems.append("The TIFF directory structure could not be read.")


def scan_bytes(data: bytes, mime_type: str) -> ByteScan:
    scan = ByteScan()
    scanners = {
        "image/jpeg": _scan_jpeg,
        "image/png": _scan_png,
        "image/webp": _scan_webp,
        "image/tiff": _scan_tiff,
    }
    scanner = scanners.get(mime_type)
    if scanner is None:
        scan.problems.append(f"No byte-level C2PA check is available for {mime_type}.")
    else:
        scanner(data, scan)
    return scan


# --- ExifTool -------------------------------------------------------------------------------


@dataclass
class ExifToolC2PA:
    found: bool
    boxes: int
    manifests: list[dict[str, Any]]
    xmp_provenance: str | None
    warnings: list[str]


def parse_exiftool_c2pa(record: dict[str, Any]) -> ExifToolC2PA:
    docs: dict[str, dict[str, Any]] = {}
    main: dict[str, Any] = {}
    for key, value in record.items():
        parts = key.split(":")
        if _DOC_ID.fullmatch(parts[0]) and len(parts) >= 3:
            docs.setdefault(parts[0], {})[parts[-1]] = value
        elif len(parts) >= 2:
            main[parts[-1]] = value

    stores = [doc for doc, tags in docs.items() if tags.get("JUMDLabel") == "c2pa"]
    manifests: list[dict[str, Any]] = []
    for store in stores:
        for doc in _children(docs, store):
            manifests.append(_describe_manifest(docs, doc))

    warnings = [str(main[name]) for name in ("Error", "Warning") if name in main]
    return ExifToolC2PA(
        found=bool(stores),
        boxes=sum(1 for tags in docs.values() if "JUMDLabel" in tags),
        manifests=manifests,
        xmp_provenance=main.get("Provenance"),
        warnings=warnings,
    )


def _children(docs: dict[str, dict[str, Any]], parent: str) -> list[str]:
    depth = parent.count("-") + 1
    children = [doc for doc in docs if doc.startswith(parent + "-") and doc.count("-") == depth]
    return sorted(children, key=lambda doc: int(doc.rsplit("-", 1)[1]))


def _payload(tags: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in tags.items() if name not in ("JUMDLabel", "JUMDType")}


def _describe_manifest(docs: dict[str, dict[str, Any]], doc: str) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "label": docs[doc].get("JUMDLabel"),
        "jumbf_type": docs[doc].get("JUMDType"),
        "claim": {},
        "assertions": [],
        "assertion_data": {},
        "signature_present": False,
    }
    for child in _children(docs, doc):
        label = str(docs[child].get("JUMDLabel", ""))
        if label.startswith("c2pa.claim"):
            manifest["claim"] = _payload(docs[child])
        elif label == "c2pa.signature":
            manifest["signature_present"] = True
        elif label == "c2pa.assertions":
            for assertion in _children(docs, child):
                assertion_label = str(docs[assertion].get("JUMDLabel", ""))
                manifest["assertions"].append(assertion_label)
                data = _payload(docs[assertion])
                if data:
                    manifest["assertion_data"][assertion_label] = data
    return manifest


# --- Combined -------------------------------------------------------------------------------


@dataclass(frozen=True)
class C2PADetection:
    present: bool
    manifest_labels: list[str]
    details: dict[str, Any]
    warnings: list[str]
    raw_output: bytes


def detect_c2pa(tool: ToolStatus, path: Path, mime_type: str, timeout: float) -> C2PADetection:
    scan = scan_bytes(path.read_bytes(), mime_type)
    record, raw = run_exiftool_json(tool, EXIFTOOL_ARGS, path, timeout)
    exiftool = parse_exiftool_c2pa(record)

    warnings = [*scan.problems, *exiftool.warnings]
    if scan.found != exiftool.found:
        warnings.append(
            "The byte-level check and ExifTool disagree about whether a C2PA manifest store is present."
        )

    manifest_labels = [str(m["label"]) for m in exiftool.manifests if m.get("label")]
    details: dict[str, Any] = {
        "detectors": {
            "byte_scan": scan.as_dict(),
            "exiftool": {"found": exiftool.found, "jumbf_boxes": exiftool.boxes},
        },
        "manifests": exiftool.manifests,
        # By the C2PA specification the last manifest in the store is the active one.
        "active_manifest_label": manifest_labels[-1] if manifest_labels else None,
        "xmp_provenance": exiftool.xmp_provenance,
    }
    return C2PADetection(
        present=scan.found or exiftool.found,
        manifest_labels=manifest_labels,
        details=details,
        warnings=warnings,
        raw_output=raw,
    )


# --- Manifest reading and validation (Milestone 4, decision D20) ------------------------------------
#
# Local validation with c2pa-python (c2pa-rs). No trust list is configured, so a "valid" result means
# the manifest's hashes and signature verify for the data they cover - it does not establish that the
# signer is trustworthy, and never that the content is truthful or unmanipulated.

# Vestigo's summary of the validator outcome for one artifact.
ValidationSummary = Literal["valid", "invalid", "unverifiable", "absent"]


def c2pa_validator_version() -> str:
    return f"c2pa-python {_dist_version('c2pa-python')} (c2pa-rs {_c2pa.sdk_version()})"


@dataclass(frozen=True)
class ManifestSummary:
    label: str
    title: str | None
    claim_generator: str | None
    signature_issuer: str | None
    signature_common_name: str | None
    signature_cert_serial: str | None
    signature_time: str | None
    signature_algorithm: str | None
    assertion_labels: list[str]
    ingredient_count: int


@dataclass(frozen=True)
class ManifestReadResult:
    status: ValidationSummary
    # The validator's own state (Trusted, Valid, Invalid) when it could read the file.
    validation_state: str | None
    manifest_count: int
    active_manifest: str | None
    manifests: list[ManifestSummary]
    # The active manifest's validation codes, grouped: success, informational, failure.
    validation_codes: dict[str, list[dict[str, str | None]]]
    # The validator's full manifest-store report, stored as a derived evidence file.
    raw_report: bytes | None
    error: str | None


def _claim_generator(manifest: dict) -> str | None:
    if manifest.get("claim_generator"):
        return str(manifest["claim_generator"])
    info = manifest.get("claim_generator_info") or []
    parts = [
        " ".join(str(entry.get(key)) for key in ("name", "version") if entry.get(key))
        for entry in info
        if isinstance(entry, dict)
    ]
    return "; ".join(part for part in parts if part) or None


def _summarize_manifest(label: str, manifest: dict) -> ManifestSummary:
    signature = manifest.get("signature_info") or {}
    return ManifestSummary(
        label=label,
        title=manifest.get("title"),
        claim_generator=_claim_generator(manifest),
        signature_issuer=signature.get("issuer"),
        signature_common_name=signature.get("common_name"),
        signature_cert_serial=signature.get("cert_serial_number"),
        signature_time=signature.get("time"),
        signature_algorithm=signature.get("alg"),
        assertion_labels=[
            str(assertion.get("label"))
            for assertion in manifest.get("assertions") or []
            if assertion.get("label")
        ],
        ingredient_count=len(manifest.get("ingredients") or []),
    )


def _grouped_codes(validation_results: dict) -> dict[str, list[dict[str, str | None]]]:
    active = validation_results.get("activeManifest") or {}
    grouped: dict[str, list[dict[str, str | None]]] = {}
    for group in ("success", "informational", "failure"):
        grouped[group] = [
            {"code": entry.get("code"), "explanation": entry.get("explanation")}
            for entry in active.get(group) or []
        ]
    return grouped


def read_manifest_store(path: Path) -> ManifestReadResult:
    """Read and validate the file's C2PA manifest store locally. Never modifies the file."""
    empty_codes: dict[str, list[dict[str, str | None]]] = {"success": [], "informational": [], "failure": []}
    try:
        reader = _c2pa.Reader(str(path))
    except Exception as exc:  # the SDK raises typed C2paError subclasses
        name = type(exc).__name__
        if "ManifestNotFound" in name:
            return ManifestReadResult("absent", None, 0, None, [], empty_codes, None, None)
        reason = "unsupported format" if "NotSupported" in name else "read error"
        return ManifestReadResult("unverifiable", None, 0, None, [], empty_codes, None, f"{reason}: {exc}")
    try:
        state = str(reader.get_validation_state())
        raw = reader.json().encode("utf-8")
        store = _json.loads(raw)
        validation_results = reader.get_validation_results() or {}
    except Exception as exc:  # noqa: BLE001 - a malformed store must be reported, not crash the stage
        reader.close()
        return ManifestReadResult(
            "unverifiable", None, 0, None, [], empty_codes, None, f"manifest store unreadable: {exc}"
        )
    reader.close()
    manifests = [
        _summarize_manifest(label, manifest) for label, manifest in (store.get("manifests") or {}).items()
    ]
    status: ValidationSummary = "valid" if state in ("Valid", "Trusted") else "invalid"
    return ManifestReadResult(
        status=status,
        validation_state=state,
        manifest_count=len(manifests),
        active_manifest=store.get("active_manifest"),
        manifests=manifests,
        validation_codes=_grouped_codes(validation_results if isinstance(validation_results, dict) else {}),
        raw_report=raw,
        error=None,
    )
