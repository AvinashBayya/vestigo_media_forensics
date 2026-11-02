"""Upload validation: the file type comes from the file's own bytes, never its name or a client header."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError


@dataclass(frozen=True)
class ImageFormat:
    name: str
    mime_type: str
    extension: str
    pillow_format: str


# Pillow's JPEG decoder also handles MPO (multi-picture JPEG from cameras).
JPEG = ImageFormat("jpeg", "image/jpeg", "jpg", "JPEG")
PNG = ImageFormat("png", "image/png", "png", "PNG")
WEBP = ImageFormat("webp", "image/webp", "webp", "WEBP")
TIFF = ImageFormat("tiff", "image/tiff", "tiff", "TIFF")
SNIFF_BYTES = 16


class InvalidImageError(Exception):
    pass


class ImageTooLargeError(Exception):
    pass


@dataclass(frozen=True)
class ImageInfo:
    format: ImageFormat
    width: int
    height: int


def sniff_image_format(head: bytes) -> ImageFormat | None:
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return TIFF
    return None


def inspect_image(path: Path, expected: ImageFormat, max_pixels: int) -> ImageInfo:
    """Confirm the file parses as the sniffed format and is within the pixel limit.

    Only the decoder for the sniffed format is allowed, so Pillow never falls back to another
    format's parser. The header is checked without decoding the full image.
    """
    try:
        with Image.open(path, formats=[expected.pillow_format]) as image:
            width, height = image.size
            if width * height > max_pixels:
                raise ImageTooLargeError(f"{width}x{height}")
            image.verify()
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError(str(exc)) from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise InvalidImageError(type(exc).__name__) from exc
    return ImageInfo(expected, width, height)
