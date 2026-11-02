"""Perceptual hashing (pHash) with imagehash."""

from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import imagehash
import PIL
from PIL import ExifTags, Image, ImageOps

# Key used in the fingerprint index.
FINGERPRINT_ALGORITHM = "phash64"
HASH_SIZE = 8
BITS = HASH_SIZE * HASH_SIZE


@dataclass(frozen=True)
class PerceptualHash:
    value: str
    frames: int
    normalization: list[str] = field(default_factory=list)


def compute_phash(path: Path) -> PerceptualHash:
    with Image.open(path) as image:
        frames = getattr(image, "n_frames", 1)
        image.seek(0)
        orientation = image.getexif().get(ExifTags.Base.Orientation)
        # For JPEG, decode at reduced resolution: the hash only uses a 32x32 thumbnail, and this
        # keeps memory low for very large images. Other formats ignore the request.
        image.draft("L", (HASH_SIZE * 32, HASH_SIZE * 32))
        upright = ImageOps.exif_transpose(image)
        value = str(imagehash.phash(upright, hash_size=HASH_SIZE))

    normalization = []
    if orientation not in (None, 1):
        normalization.append(f"Rotated/flipped upright using EXIF orientation {orientation}.")
    if frames > 1:
        normalization.append(f"First of {frames} frames used.")
    normalization.append("Converted to greyscale and reduced to 32x32 pixels before hashing.")
    return PerceptualHash(value=value, frames=frames, normalization=normalization)


def hamming_distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


def imagehash_version() -> str:
    return f"{version('ImageHash')} (Pillow {PIL.__version__})"
