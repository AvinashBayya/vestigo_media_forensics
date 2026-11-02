"""Text extraction with Tesseract."""

from dataclasses import dataclass
from pathlib import Path

from PIL import ExifTags, Image, ImageOps

from app.core.tools import ToolError, ToolOutputError, ToolStatus, run_tool

# Milestone 1 decision D-4: English only.
LANGUAGES = ("eng",)
# Fully automatic page segmentation.
PAGE_SEGMENTATION_MODE = "3"


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None
    word_count: int
    preprocessing: list[str]
    tsv: bytes


def prepare_image(source: Path, target: Path) -> list[str]:
    """Write an upright, opaque RGB PNG copy for Tesseract and describe what was changed."""
    notes: list[str] = []
    with Image.open(source) as image:
        frames = getattr(image, "n_frames", 1)
        image.seek(0)
        orientation = image.getexif().get(ExifTags.Base.Orientation)
        upright = ImageOps.exif_transpose(image)
        if upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info:
            rgba = upright.convert("RGBA")
            upright = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
            notes.append("Transparent areas placed on a white background.")
        upright.convert("RGB").save(target, format="PNG")
    if orientation not in (None, 1):
        notes.insert(0, f"Rotated/flipped upright using EXIF orientation {orientation}.")
    if frames > 1:
        notes.insert(0, f"First of {frames} frames used.")
    notes.append("Converted to an 8-bit RGB PNG.")
    return notes


def parse_tsv(tsv: bytes) -> tuple[float | None, int]:
    """Return (mean word confidence on a 0–1 scale, word count) from Tesseract TSV output."""
    lines = tsv.decode("utf-8", errors="replace").splitlines()
    if not lines:
        raise ToolOutputError("Tesseract produced no TSV output.")
    header = lines[0].split("\t")
    try:
        level, conf, text = header.index("level"), header.index("conf"), header.index("text")
    except ValueError as exc:
        raise ToolOutputError("Tesseract TSV output has an unexpected header.") from exc

    confidences: list[float] = []
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) <= text or columns[level] != "5" or not columns[text].strip():
            continue
        value = float(columns[conf])
        if value >= 0:
            confidences.append(value)
    if not confidences:
        return None, 0
    return round(sum(confidences) / len(confidences) / 100, 4), len(confidences)


def run_ocr(tool: ToolStatus, source: Path, scratch_dir: Path, timeout: float) -> OCRResult:
    prepared = scratch_dir / "ocr-input.png"
    preprocessing = prepare_image(source, prepared)
    output_base = scratch_dir / "ocr-output"
    args = [prepared, output_base, "-l", "+".join(LANGUAGES), "--psm", PAGE_SEGMENTATION_MODE, "txt", "tsv"]
    completed = run_tool(tool, args, timeout=timeout)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = stderr[-1] if stderr else "no error output"
        raise ToolError(f"Tesseract exited with code {completed.returncode} ({detail}).")
    try:
        text = output_base.with_suffix(".txt").read_text(encoding="utf-8", errors="replace").strip()
        tsv = output_base.with_suffix(".tsv").read_bytes()
    except FileNotFoundError as exc:
        raise ToolOutputError("Tesseract did not write its output files.") from exc
    confidence, word_count = parse_tsv(tsv)
    return OCRResult(text, confidence, word_count, preprocessing, tsv)
