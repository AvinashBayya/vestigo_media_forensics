"""Text extraction with Tesseract, with conservative Pillow preprocessing (decision D13).

Two passes are run on copies of the image; the original file is only read:

- pass A ("grayscale"): upright, greyscale, and upscaled if the image is small;
- pass B ("threshold"): the same image after a local-mean adaptive threshold.

Pass B is used only when the selection rule in `select_pass` says it is clearly better. Both
passes are reported as evidence, whichever is selected.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import PIL
from PIL import ExifTags, Image, ImageChops, ImageFilter, ImageOps

from app.core.tools import ToolError, ToolOutputError, ToolStatus, run_tool

# Milestone 1 decision D-4: English only.
LANGUAGES = ("eng",)
# Fully automatic page segmentation.
PAGE_SEGMENTATION_MODE = "3"

# Upscaling: the largest whole-number factor up to MAX_UPSCALE_FACTOR that keeps the longest side
# at or below UPSCALE_TARGET_SIDE. Images whose longest side is already above half the target are
# not upscaled.
MAX_UPSCALE_FACTOR = 3
UPSCALE_TARGET_SIDE = 2000

# Adaptive threshold: a pixel becomes black when it is more than THRESHOLD_OFFSET grey levels darker
# than the mean of its neighbourhood (a box of THRESHOLD_RADIUS pixels each side, at the original
# scale, multiplied by the upscale factor).
THRESHOLD_RADIUS = 15
THRESHOLD_OFFSET = 20

# Selection rule for pass B (threshold) over pass A (grayscale).
MIN_CONFIDENCE_GAIN = 0.05
MIN_WORD_RETENTION = 0.8
MIN_CONFIDENCE_WITHOUT_PASS_A_WORDS = 0.70

Variant = Literal["grayscale", "threshold"]


@dataclass(frozen=True)
class PreprocessingStep:
    step: str
    applied: bool
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Recognition:
    text: str
    confidence: float | None
    word_count: int
    tsv: bytes


@dataclass(frozen=True)
class OCRPass:
    variant: Variant
    image_png: bytes
    recognition: Recognition | None
    error: str | None = None

    def candidate(self) -> dict[str, Any]:
        found = self.recognition
        return {
            "variant": self.variant,
            "status": "succeeded" if found else "failed",
            "text": found.text if found else None,
            "confidence": found.confidence if found else None,
            "word_count": found.word_count if found else None,
            "error": self.error,
        }


@dataclass(frozen=True)
class CleaningRule:
    rule: str
    description: str
    lines_affected: int


@dataclass(frozen=True)
class OCRResult:
    text: str
    cleaned_text: str | None
    cleaning: list[CleaningRule]
    confidence: float | None
    word_count: int
    preprocessing: list[PreprocessingStep]
    passes: list[OCRPass]
    selected: Variant
    selection_reason: str

    @property
    def variant_error(self) -> str | None:
        return next((p.error for p in self.passes if p.variant == "threshold" and p.error), None)

    def payload(self) -> dict[str, Any]:
        return {
            "engine": "tesseract",
            "languages": list(LANGUAGES),
            "text": self.text,
            "cleaned_text": self.cleaned_text,
            "cleaning": [asdict(rule) for rule in self.cleaning],
            "confidence": self.confidence,
            "word_count": self.word_count,
            "preprocessing": [asdict(step) for step in self.preprocessing],
            "candidates": [p.candidate() for p in self.passes],
            "selected": {"variant": self.selected, "reason": self.selection_reason},
        }


def pillow_version() -> str:
    return PIL.__version__


def load_upright(source: Path) -> tuple[Image.Image, list[PreprocessingStep]]:
    """Return an upright, opaque RGB copy of the first frame, and the steps that describe it."""
    with Image.open(source) as image:
        frames = getattr(image, "n_frames", 1)
        image.seek(0)
        orientation = image.getexif().get(ExifTags.Base.Orientation)
        upright = ImageOps.exif_transpose(image)
        transparent = upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info
        if transparent:
            rgba = upright.convert("RGBA")
            upright = Image.alpha_composite(Image.new("RGBA", rgba.size, "white"), rgba)
        rgb = upright.convert("RGB")
    rotated = orientation not in (None, 1)
    steps = [
        PreprocessingStep(
            "first_frame",
            frames > 1,
            f"First of {frames} frames used." if frames > 1 else "Single-frame image.",
            {"frames": frames},
        ),
        PreprocessingStep(
            "exif_orientation",
            rotated,
            f"Rotated/flipped upright using EXIF orientation {orientation}."
            if rotated
            else "No EXIF rotation needed.",
            {"orientation": orientation},
        ),
        PreprocessingStep(
            "flatten_transparency",
            transparent,
            "Transparent areas placed on a white background." if transparent else "No transparency.",
            {"background": "white"},
        ),
    ]
    return rgb, steps


def to_grayscale(image: Image.Image) -> tuple[Image.Image, PreprocessingStep]:
    gray = image.convert("L")
    return gray, PreprocessingStep(
        "grayscale",
        True,
        "Converted to 8-bit greyscale.",
        {"mode": "L", "formula": "ITU-R 601-2 luma (Pillow convert('L'))"},
    )


def upscale_factor(width: int, height: int) -> int:
    longest = max(width, height)
    factor = 1
    while factor < MAX_UPSCALE_FACTOR and longest * (factor + 1) <= UPSCALE_TARGET_SIDE:
        factor += 1
    return factor


def upscale(image: Image.Image) -> tuple[Image.Image, int, PreprocessingStep]:
    factor = upscale_factor(*image.size)
    scaled = (
        image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
        if factor > 1
        else image
    )
    parameters = {
        "factor": factor,
        "resample": "LANCZOS",
        "max_factor": MAX_UPSCALE_FACTOR,
        "target_longest_side": UPSCALE_TARGET_SIDE,
        "input_size": list(image.size),
        "output_size": list(scaled.size),
    }
    description = (
        f"Upscaled {factor}x (Lanczos) because the image is small."
        if factor > 1
        else "Not upscaled: the image is large enough."
    )
    return scaled, factor, PreprocessingStep("upscale", factor > 1, description, parameters)


def adaptive_threshold(gray: Image.Image, radius: int) -> tuple[Image.Image, PreprocessingStep]:
    """Black where a pixel is more than THRESHOLD_OFFSET levels darker than its local mean, else white."""
    local_mean = gray.filter(ImageFilter.BoxBlur(radius))
    darker_by = ImageChops.subtract(local_mean, gray)
    binary = darker_by.point(lambda value: 0 if value > THRESHOLD_OFFSET else 255)
    return binary, PreprocessingStep(
        "adaptive_threshold",
        True,
        "Local-mean adaptive threshold, used as the input of the threshold pass only.",
        {
            "method": "local mean (Pillow BoxBlur)",
            "window_radius_px": radius,
            "offset": THRESHOLD_OFFSET,
            "polarity": "dark text on a lighter background",
            "applies_to": "threshold",
        },
    )


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


def recognize(tool: ToolStatus, image_path: Path, output_base: Path, timeout: float) -> Recognition:
    """Run Tesseract once on a prepared image file."""
    args = [image_path, output_base, "-l", "+".join(LANGUAGES), "--psm", PAGE_SEGMENTATION_MODE, "txt", "tsv"]
    completed = run_tool(tool, args, timeout=timeout)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
        detail = stderr[-1] if stderr else "no error output"
        raise ToolError(f"Tesseract exited with code {completed.returncode} ({detail}).")
    try:
        # Only the trailing page separator and surrounding whitespace are removed.
        text = output_base.with_suffix(".txt").read_text(encoding="utf-8", errors="replace").strip()
        tsv = output_base.with_suffix(".tsv").read_bytes()
    except FileNotFoundError as exc:
        raise ToolOutputError("Tesseract did not write its output files.") from exc
    confidence, word_count = parse_tsv(tsv)
    return Recognition(text, confidence, word_count, tsv)


def select_pass(grayscale: Recognition, threshold: Recognition | None) -> tuple[Variant, str]:
    """The conservative rule from decision D13. Returns the selected variant and the reason."""
    if threshold is None:
        return "grayscale", "The threshold pass failed, so the grayscale pass is used."
    if grayscale.word_count == 0:
        minimum = MIN_CONFIDENCE_WITHOUT_PASS_A_WORDS
        if threshold.word_count > 0 and (threshold.confidence or 0) >= minimum:
            return "threshold", (
                f"The grayscale pass found no words; the threshold pass found {threshold.word_count} with "
                f"mean confidence {threshold.confidence:.2f} (minimum {minimum:.2f})."
            )
        return "grayscale", (
            "Neither pass found words with enough confidence "
            f"(the threshold pass needs at least {MIN_CONFIDENCE_WITHOUT_PASS_A_WORDS:.2f} when the "
            "grayscale pass finds none)."
        )
    gain = round((threshold.confidence or 0) - (grayscale.confidence or 0), 4)
    retention = threshold.word_count / grayscale.word_count
    if gain >= MIN_CONFIDENCE_GAIN and retention >= MIN_WORD_RETENTION:
        return "threshold", (
            f"The threshold pass raised mean confidence by {gain:.2f} (minimum {MIN_CONFIDENCE_GAIN:.2f}) "
            f"and kept {threshold.word_count} of {grayscale.word_count} words "
            f"(minimum {MIN_WORD_RETENTION:.0%})."
        )
    if gain < MIN_CONFIDENCE_GAIN:
        why = f"its confidence gain was {gain:.2f}, below the minimum of {MIN_CONFIDENCE_GAIN:.2f}"
    else:
        why = (
            f"it kept only {threshold.word_count} of {grayscale.word_count} words, below the minimum of "
            f"{MIN_WORD_RETENTION:.0%}"
        )
    return "grayscale", f"The threshold pass was not used: {why}."


def clean_text(raw: str) -> tuple[str | None, list[CleaningRule]]:
    """Cosmetic cleaning. Never removes a line that contains a letter or digit (str.isalnum).

    Returns (cleaned text, rules that changed it), or (None, []) when nothing changed.
    """
    lines = raw.split("\n")
    rules: list[CleaningRule] = []

    kept = [line for line in lines if not line.strip() or any(char.isalnum() for char in line)]
    if removed := len(lines) - len(kept):
        rules.append(
            CleaningRule(
                "remove_symbol_only_lines",
                "Removed lines that contain only symbols or punctuation (no letters or digits).",
                removed,
            )
        )

    trimmed = [line.rstrip() for line in kept]
    if changed := sum(1 for before, after in zip(kept, trimmed, strict=True) if before != after):
        rules.append(CleaningRule("strip_trailing_whitespace", "Removed trailing whitespace.", changed))

    collapsed: list[str] = []
    dropped = 0
    for line in trimmed:
        if not line and (not collapsed or not collapsed[-1]):
            dropped += 1
            continue
        collapsed.append(line)
    while collapsed and not collapsed[-1]:
        collapsed.pop()
        dropped += 1
    if dropped:
        rules.append(
            CleaningRule(
                "collapse_blank_lines",
                "Collapsed runs of blank lines to one, and removed blank lines at the start and end.",
                dropped,
            )
        )

    cleaned = "\n".join(collapsed)
    if cleaned == raw:
        return None, []
    return cleaned, rules


def _save_png(image: Image.Image, path: Path) -> bytes:
    image.save(path, format="PNG")
    return path.read_bytes()


def run_ocr(tool: ToolStatus, source: Path, scratch_dir: Path, timeout: float) -> OCRResult:
    """Run both passes. Pass A failing raises ToolError; pass B failing is recorded on its pass."""
    upright, steps = load_upright(source)
    gray, gray_step = to_grayscale(upright)
    scaled, factor, upscale_step = upscale(gray)
    steps += [gray_step, upscale_step]

    gray_path = scratch_dir / "ocr-grayscale.png"
    gray_png = _save_png(scaled, gray_path)
    pass_a = recognize(tool, gray_path, scratch_dir / "ocr-grayscale", timeout)
    passes = [OCRPass("grayscale", gray_png, pass_a)]

    threshold_png = b""
    pass_b: Recognition | None = None
    error: str | None = None
    try:
        binary, threshold_step = adaptive_threshold(scaled, THRESHOLD_RADIUS * factor)
        steps.append(threshold_step)
        threshold_path = scratch_dir / "ocr-threshold.png"
        threshold_png = _save_png(binary, threshold_path)
        pass_b = recognize(tool, threshold_path, scratch_dir / "ocr-threshold", timeout)
    except ToolError as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - pass B is optional; its failure is recorded, not raised
        error = f"{type(exc).__name__}: {exc}"
    passes.append(OCRPass("threshold", threshold_png, pass_b, error))

    selected, reason = select_pass(pass_a, pass_b)
    chosen = pass_b if selected == "threshold" and pass_b is not None else pass_a
    cleaned, rules = clean_text(chosen.text)
    return OCRResult(
        text=chosen.text,
        cleaned_text=cleaned,
        cleaning=rules,
        confidence=chosen.confidence,
        word_count=chosen.word_count,
        preprocessing=steps,
        passes=passes,
        selected=selected,
        selection_reason=reason,
    )
