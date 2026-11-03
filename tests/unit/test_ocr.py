from pathlib import Path

import pytest
from PIL import Image

from app.core.tools import ToolError, ToolOutputError, ToolRegistry, ToolStatus
from app.services import ocr
from app.services.ocr import (
    Recognition,
    adaptive_threshold,
    clean_text,
    load_upright,
    parse_tsv,
    run_ocr,
    select_pass,
    upscale_factor,
)
from tests.fixtures.make_fixtures import OCR_SCREENSHOT_WORDS, OCR_TEXT, FixtureSet
from tests.fixtures.measure_ocr import baseline_ocr, expected_words, words_recovered


@pytest.fixture(scope="module")
def tesseract() -> ToolStatus:
    return ToolRegistry().require("tesseract")


def step(result: ocr.OCRResult, name: str) -> ocr.PreprocessingStep:
    return next(s for s in result.preprocessing if s.step == name)


def before_and_after(
    tesseract: ToolStatus, fixtures: FixtureSet, case: str, tmp_path: Path
) -> tuple[int, int, ocr.OCRResult]:
    source, words = expected_words(fixtures)[case]
    (tmp_path / "before").mkdir()
    (tmp_path / "after").mkdir()
    before = baseline_ocr(tesseract, source, tmp_path / "before")
    after = run_ocr(tesseract, source, tmp_path / "after", timeout=120)
    return words_recovered(before.text, words), words_recovered(after.text, words), after


# --- Fixture images: measured before/after word recovery (docs/09-DECISIONS.md D13) ---------------


def test_clean_rendered_text_has_no_regression(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path
) -> None:
    before, after, result = before_and_after(tesseract, fixtures, "clean", tmp_path)

    assert after >= before == len(OCR_TEXT.split())
    assert result.selected == "grayscale"
    assert step(result, "upscale").applied is False
    assert step(result, "grayscale").applied is True
    assert result.confidence is not None and 0.5 < result.confidence <= 1.0


def test_screenshot_text_improves_and_keeps_light_on_dark_text(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path
) -> None:
    # Stable gain: 9 -> 11 of 11 words, at both 2x and 3x upscaling.
    before, after, result = before_and_after(tesseract, fixtures, "screenshot", tmp_path)

    assert after > before
    assert after == len(OCR_SCREENSHOT_WORDS)
    # White text on the dark title bar and on the button must survive pass selection.
    assert words_recovered(result.text, ("Case", "Dashboard", "Download", "Report")) == 4
    assert step(result, "upscale").parameters["factor"] == 2


def test_low_resolution_text_is_upscaled_without_regression(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path
) -> None:
    # Measured 0 -> 5 of 5, but a 9 px variant regresses (5 -> 4), so only "no regression" is asserted.
    before, after, result = before_and_after(tesseract, fixtures, "low_res", tmp_path)

    assert after >= before
    upscale = step(result, "upscale")
    assert upscale.applied is True
    assert upscale.parameters["factor"] == 3
    assert upscale.parameters["input_size"] == [150, 20]
    assert upscale.parameters["output_size"] == [450, 60]
    assert upscale.parameters["resample"] == "LANCZOS"


def test_noisy_stylised_text_improves_through_the_threshold_pass(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path
) -> None:
    # Stable gain: 0 -> 4 of 4 words; the threshold pass found all words at 1x, 2x and 3x.
    before, after, result = before_and_after(tesseract, fixtures, "noisy", tmp_path)

    assert after > before
    assert result.selected == "threshold"
    assert "grayscale pass found no words" in result.selection_reason
    grayscale, threshold = result.passes
    assert grayscale.recognition is not None and grayscale.recognition.word_count == 0
    assert threshold.recognition is not None and threshold.recognition.word_count >= 4
    parameters = step(result, "adaptive_threshold").parameters
    assert parameters["offset"] == ocr.THRESHOLD_OFFSET
    assert (
        parameters["window_radius_px"] == ocr.THRESHOLD_RADIUS * step(result, "upscale").parameters["factor"]
    )


@pytest.mark.parametrize("case", ["blank", "textured_no_text"])
def test_image_without_text_returns_an_empty_result(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path, case: str
) -> None:
    source, _ = expected_words(fixtures)[case]
    result = run_ocr(tesseract, source, tmp_path, timeout=120)

    assert result.text == ""
    assert result.cleaned_text is None
    assert result.cleaning == []
    assert result.word_count == 0
    assert result.confidence is None
    assert result.selected == "grayscale"
    assert [p.recognition.word_count for p in result.passes if p.recognition] == [0, 0]


def test_both_passes_are_reported(tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path) -> None:
    result = run_ocr(tesseract, fixtures.ocr_text, tmp_path, timeout=120)
    payload = result.payload()

    assert [c["variant"] for c in payload["candidates"]] == ["grayscale", "threshold"]
    assert all(c["status"] == "succeeded" and c["error"] is None for c in payload["candidates"])
    assert payload["selected"]["variant"] == "grayscale"
    assert payload["selected"]["reason"]
    assert [s["step"] for s in payload["preprocessing"]] == [
        "first_frame",
        "exif_orientation",
        "flatten_transparency",
        "grayscale",
        "upscale",
        "adaptive_threshold",
    ]
    for ocr_pass in result.passes:
        assert ocr_pass.image_png.startswith(b"\x89PNG")
        assert ocr_pass.recognition is not None and ocr_pass.recognition.tsv.startswith(b"level\t")


def test_original_file_is_not_modified(tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path) -> None:
    before = fixtures.ocr_low_res.read_bytes()
    run_ocr(tesseract, fixtures.ocr_low_res, tmp_path, timeout=120)
    assert fixtures.ocr_low_res.read_bytes() == before
    assert {p.name for p in tmp_path.iterdir()} >= {"ocr-grayscale.png", "ocr-threshold.png"}


# --- Pass failures ------------------------------------------------------------------------------


def failing_on(variant: str, real=ocr.recognize):
    def fake(tool: ToolStatus, image_path: Path, output_base: Path, timeout: float) -> Recognition:
        if variant in image_path.name:
            raise ToolError("Tesseract exited with code 1 (boom).")
        return real(tool, image_path, output_base, timeout)

    return fake


def test_threshold_pass_failure_is_recorded_and_grayscale_is_used(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "recognize", failing_on("threshold"))

    result = run_ocr(tesseract, fixtures.ocr_text, tmp_path, timeout=120)

    assert result.variant_error == "Tesseract exited with code 1 (boom)."
    assert result.selected == "grayscale"
    assert "threshold pass failed" in result.selection_reason
    candidates = result.payload()["candidates"]
    assert candidates[1] == {
        "variant": "threshold",
        "status": "failed",
        "text": None,
        "confidence": None,
        "word_count": None,
        "error": "Tesseract exited with code 1 (boom).",
    }
    assert "VESTIGO" in result.text.upper()


def test_grayscale_pass_failure_raises(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ocr, "recognize", failing_on("grayscale"))
    with pytest.raises(ToolError):
        run_ocr(tesseract, fixtures.ocr_text, tmp_path, timeout=120)


# --- Selection rule -----------------------------------------------------------------------------


def recognition(confidence: float | None, words: int) -> Recognition:
    return Recognition(text="x" if words else "", confidence=confidence, word_count=words, tsv=b"")


@pytest.mark.parametrize(
    ("grayscale", "threshold", "selected"),
    [
        (recognition(0.80, 10), recognition(0.85, 10), "threshold"),  # gain exactly 0.05
        (recognition(0.80, 10), recognition(0.8499, 10), "grayscale"),  # gain below 0.05
        (recognition(0.80, 10), recognition(0.95, 8), "threshold"),  # keeps exactly 80% of words
        (recognition(0.80, 10), recognition(0.95, 7), "grayscale"),  # keeps 70%: dropped words
        (recognition(None, 0), recognition(0.70, 3), "threshold"),  # pass A empty, B at minimum
        (recognition(None, 0), recognition(0.69, 3), "grayscale"),  # pass A empty, B below minimum
        (recognition(None, 0), recognition(None, 0), "grayscale"),
        (recognition(0.80, 10), None, "grayscale"),  # pass B failed
    ],
)
def test_select_pass(grayscale: Recognition, threshold: Recognition | None, selected: str) -> None:
    variant, reason = select_pass(grayscale, threshold)
    assert variant == selected
    assert reason


def test_select_pass_explains_why_the_threshold_pass_was_rejected() -> None:
    _, reason = select_pass(recognition(0.80, 10), recognition(0.95, 7))
    assert "kept only 7 of 10 words" in reason
    _, reason = select_pass(recognition(0.80, 10), recognition(0.82, 10))
    assert "confidence gain was 0.02" in reason


# --- Preprocessing ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("size", "factor"),
    [((150, 20), 3), ((666, 100), 3), ((667, 100), 2), ((900, 360), 2), ((1000, 50), 2), ((1001, 50), 1)],
)
def test_upscale_factor_is_capped(size: tuple[int, int], factor: int) -> None:
    assert upscale_factor(*size) == factor
    assert factor <= ocr.MAX_UPSCALE_FACTOR
    assert factor == 1 or max(size) * factor <= ocr.UPSCALE_TARGET_SIDE


def test_adaptive_threshold_is_binary_and_records_parameters() -> None:
    gray = Image.new("L", (64, 64), 200)
    gray.paste(40, (20, 20, 30, 40))
    binary, info = adaptive_threshold(gray, radius=5)
    histogram = binary.histogram()
    assert sum(histogram[1:255]) == 0
    assert histogram[0] and histogram[255]
    assert info.parameters["window_radius_px"] == 5
    assert info.parameters["offset"] == ocr.THRESHOLD_OFFSET
    assert info.parameters["applies_to"] == "threshold"


def test_load_upright_flattens_transparency_and_applies_orientation(
    fixtures: FixtureSet, tmp_path: Path
) -> None:
    transparent = tmp_path / "transparent.png"
    Image.new("RGBA", (20, 10), (0, 0, 0, 0)).save(transparent)

    image, steps = load_upright(transparent)
    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert {s.step: s.applied for s in steps}["flatten_transparency"] is True

    image, steps = load_upright(fixtures.oriented)
    assert image.size == (640, 480)
    orientation = next(s for s in steps if s.step == "exif_orientation")
    assert orientation.applied is True
    assert orientation.parameters == {"orientation": 6}


# --- Cleaning -----------------------------------------------------------------------------------


def test_cleaning_removes_only_symbol_only_lines_and_whitespace() -> None:
    raw = "Report 7  \n|\n— ~ —\n\n\n\nItem: é\n日本\n. a\n—\n7\n\n"

    cleaned, rules = clean_text(raw)

    assert cleaned == "Report 7\n\nItem: é\n日本\n. a\n7"
    assert [(r.rule, r.lines_affected) for r in rules] == [
        ("remove_symbol_only_lines", 3),
        ("strip_trailing_whitespace", 1),
        ("collapse_blank_lines", 4),
    ]


@pytest.mark.parametrize("line", ["a", "7", "é", "日本", "-- 1 --", "(x)", "Ⅻ"])
def test_cleaning_never_removes_a_line_with_alphanumeric_characters(line: str) -> None:
    cleaned, _ = clean_text(f"{line}\n|||")
    assert cleaned == line


def test_cleaning_that_changes_nothing_returns_none() -> None:
    assert clean_text("Hello world\n\nSecond paragraph") == (None, [])
    assert clean_text("") == (None, [])


def test_parse_tsv() -> None:
    tsv = (
        b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        b"1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t\n"
        b"5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t90.0\tHello\n"
        b"5\t1\t1\t1\t1\t2\t0\t0\t10\t10\t70.0\tworld\n"
        b"5\t1\t1\t1\t1\t3\t0\t0\t10\t10\t95.0\t \n"
    )
    assert parse_tsv(tsv) == (0.8, 2)

    with pytest.raises(ToolOutputError):
        parse_tsv(b"")
    with pytest.raises(ToolOutputError):
        parse_tsv(b"something else\n")
