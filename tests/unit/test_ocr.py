from pathlib import Path

import pytest
from PIL import Image

from app.core.tools import ToolOutputError, ToolRegistry, ToolStatus
from app.services.ocr import parse_tsv, prepare_image, run_ocr
from tests.fixtures.make_fixtures import OCR_TEXT, FixtureSet


@pytest.fixture(scope="module")
def tesseract() -> ToolStatus:
    return ToolRegistry().require("tesseract")


def test_clear_text_is_extracted(tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path) -> None:
    result = run_ocr(tesseract, fixtures.ocr_text, tmp_path, timeout=60)

    words = result.text.upper().split()
    for expected in OCR_TEXT.split():
        assert expected in words
    assert result.word_count >= len(OCR_TEXT.split())
    assert result.confidence is not None and 0.5 < result.confidence <= 1.0
    assert result.tsv.startswith(b"level\t")


def test_image_without_text_returns_an_empty_result(
    tesseract: ToolStatus, fixtures: FixtureSet, tmp_path: Path
) -> None:
    result = run_ocr(tesseract, fixtures.blank, tmp_path, timeout=60)

    assert result.text == ""
    assert result.word_count == 0
    assert result.confidence is None


def test_prepare_image_flattens_transparency_and_applies_orientation(
    fixtures: FixtureSet, tmp_path: Path
) -> None:
    transparent = tmp_path / "transparent.png"
    Image.new("RGBA", (20, 10), (0, 0, 0, 0)).save(transparent)

    notes = prepare_image(transparent, tmp_path / "out.png")
    with Image.open(tmp_path / "out.png") as out:
        assert out.mode == "RGB"
        assert out.getpixel((0, 0)) == (255, 255, 255)
    assert any("white background" in note for note in notes)

    notes = prepare_image(fixtures.oriented, tmp_path / "oriented.png")
    with Image.open(tmp_path / "oriented.png") as out:
        assert out.size == (640, 480)
    assert any("orientation 6" in note for note in notes)


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
