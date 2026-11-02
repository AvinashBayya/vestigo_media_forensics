import hashlib
from pathlib import Path

import pytest

from app.services.artifacts import sanitize_filename
from app.services.hashing import hash_file
from app.services.validation import (
    JPEG,
    PNG,
    TIFF,
    WEBP,
    ImageTooLargeError,
    InvalidImageError,
    inspect_image,
    sniff_image_format,
)
from tests.fixtures.make_fixtures import FixtureSet


def test_formats_are_sniffed_from_content(fixtures: FixtureSet) -> None:
    def head(path: Path) -> bytes:
        return path.read_bytes()[:16]

    assert sniff_image_format(head(fixtures.jpeg)) is JPEG
    assert sniff_image_format(head(fixtures.png)) is PNG
    assert sniff_image_format(head(fixtures.webp)) is WEBP
    assert sniff_image_format(head(fixtures.tiff)) is TIFF
    assert sniff_image_format(head(fixtures.gif)) is None
    assert sniff_image_format(head(fixtures.html_named_jpg)) is None
    assert sniff_image_format(b"") is None


def test_inspect_image_reads_dimensions(fixtures: FixtureSet) -> None:
    info = inspect_image(fixtures.webp, WEBP, max_pixels=1_000_000)
    assert (info.width, info.height) == (640, 480)


def test_inspect_image_rejects_content_that_does_not_parse_as_the_sniffed_format(
    fixtures: FixtureSet,
) -> None:
    with pytest.raises(InvalidImageError):
        inspect_image(fixtures.truncated_jpeg, JPEG, max_pixels=1_000_000)
    with pytest.raises(InvalidImageError):
        inspect_image(fixtures.png, JPEG, max_pixels=1_000_000)


def test_inspect_image_enforces_the_pixel_limit(fixtures: FixtureSet) -> None:
    with pytest.raises(ImageTooLargeError):
        inspect_image(fixtures.jpeg, JPEG, max_pixels=640 * 480 - 1)
    inspect_image(fixtures.jpeg, JPEG, max_pixels=640 * 480)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "upload"),
        ("", "upload"),
        ("photo.jpg", "photo.jpg"),
        ("dir/sub/photo.jpg", "photo.jpg"),
        ("C:\\Users\\a\\photo.jpg", "photo.jpg"),
        ("bad\x00name\x1f.png", "badname.png"),
        ("  spaced.png  ", "spaced.png"),
        ("a" * 300 + ".jpg", "a" * 255),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    assert sanitize_filename(raw) == expected


def test_hash_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"abc" * 1_000_000)

    hashes = hash_file(path)

    assert hashes.sha256 == hashlib.sha256(b"abc" * 1_000_000).hexdigest()
    assert hashes.md5 == hashlib.md5(b"abc" * 1_000_000).hexdigest()
    assert hashes.size_bytes == 3_000_000


def test_same_content_same_hashes_and_different_content_different_hashes(fixtures: FixtureSet) -> None:
    assert hash_file(fixtures.jpeg) == hash_file(fixtures.jpeg)
    assert hash_file(fixtures.jpeg).sha256 != hash_file(fixtures.png).sha256
    assert hash_file(fixtures.jpeg).md5 != hash_file(fixtures.png).md5
