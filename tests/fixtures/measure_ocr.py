"""Word recovery of the OCR fixtures before and after two-pass preprocessing (decision D13).

"Before" is the Milestone 1 behaviour prior to D13: one Tesseract pass on an upright, opaque RGB
copy of the image. "After" is `run_ocr`. To print the table used in docs/09-DECISIONS.md:

    python -m tests.fixtures.measure_ocr
"""

import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from app.core.tools import ToolRegistry, ToolStatus
from app.services.ocr import Recognition, load_upright, recognize, run_ocr
from tests.fixtures.make_fixtures import (
    OCR_LOW_RES_TEXT,
    OCR_NOISY_TEXT,
    OCR_SCREENSHOT_WORDS,
    OCR_TEXT,
    FixtureSet,
    build_fixtures,
    font,
)


def expected_words(fixtures: FixtureSet) -> dict[str, tuple[Path, tuple[str, ...]]]:
    return {
        "clean": (fixtures.ocr_text, tuple(OCR_TEXT.split())),
        "screenshot": (fixtures.ocr_screenshot, OCR_SCREENSHOT_WORDS),
        "low_res": (fixtures.ocr_low_res, tuple(OCR_LOW_RES_TEXT.split())),
        "noisy": (fixtures.ocr_noisy, tuple(OCR_NOISY_TEXT.split())),
        "blank": (fixtures.blank, ()),
        "textured_no_text": (fixtures.unrelated, ()),
    }


def words_recovered(text: str, words: tuple[str, ...]) -> int:
    """How many of the expected words appear as whole tokens (case-insensitive) in the OCR text."""
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+", text)}
    return sum(word.lower() in tokens for word in words)


def baseline_ocr(tool: ToolStatus, source: Path, scratch: Path) -> Recognition:
    """The pre-D13 behaviour: Tesseract once on an upright RGB PNG copy."""
    upright, _ = load_upright(source)
    prepared = scratch / "baseline.png"
    upright.save(prepared, format="PNG")
    return recognize(tool, prepared, scratch / "baseline", timeout=120)


@dataclass(frozen=True)
class Measurement:
    case: str
    expected: int
    before: int
    after: int
    before_confidence: float | None
    after_confidence: float | None
    selected: str
    upscale_factor: int


def measure(tool: ToolStatus, case: str, source: Path, words: tuple[str, ...]) -> Measurement:
    with tempfile.TemporaryDirectory() as before_dir, tempfile.TemporaryDirectory() as after_dir:
        before = baseline_ocr(tool, source, Path(before_dir))
        after = run_ocr(tool, source, Path(after_dir), timeout=120)
    factor = next(step.parameters["factor"] for step in after.preprocessing if step.step == "upscale")
    return Measurement(
        case,
        len(words),
        words_recovered(before.text, words),
        words_recovered(after.text, words),
        before.confidence,
        after.confidence,
        after.selected,
        factor,
    )


def nine_pixel_text(path: Path) -> Path:
    """Not a test fixture: a 9 px variant of the low-res text, measured because upscaling misreads it."""
    image = Image.new("RGB", (170, 24), "white")
    ImageDraw.Draw(image).text((4, 7), OCR_LOW_RES_TEXT, fill=(20, 20, 20), font=font("DejaVuSans.ttf", 9))
    image.save(path)
    return path


def main() -> None:
    tool = ToolRegistry().require("tesseract")
    with tempfile.TemporaryDirectory() as directory:
        fixtures = build_fixtures(Path(directory))
        cases = expected_words(fixtures)
        cases["low_res_9px"] = (
            nine_pixel_text(Path(directory) / "nine.png"),
            tuple(OCR_LOW_RES_TEXT.split()),
        )
        print("| Image | Expected words | Before | After | Confidence before → after | Pass used | Upscale |")
        print("|---|---|---|---|---|---|---|")
        for case, (source, words) in cases.items():
            m = measure(tool, case, source, words)
            confidence = f"{m.before_confidence} → {m.after_confidence}"
            print(
                f"| {m.case} | {m.expected} | {m.before} | {m.after} | {confidence} | {m.selected} "
                f"| {m.upscale_factor}x |"
            )
    sys.stdout.flush()


if __name__ == "__main__":
    main()
