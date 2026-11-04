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


# Dihedral orientation variants (decision D19): the same pHash computed on rotated and mirrored
# copies of the upright image, so duplicate search can also find rotated or mirrored copies.
# Rotations are counter-clockwise. The canonical hash and the fingerprint indexes are unchanged.
ORIENTATION_VARIANTS: tuple[tuple[str, int, bool], ...] = (
    ("rot90", 90, False),
    ("rot180", 180, False),
    ("rot270", 270, False),
    ("mirror", 0, True),
    ("mirror_rot90", 90, True),
    ("mirror_rot180", 180, True),
    ("mirror_rot270", 270, True),
)

_ROTATIONS = {
    90: Image.Transpose.ROTATE_90,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_270,
}


@dataclass(frozen=True)
class OrientationHashes:
    # The canonical (upright) hash, identical to compute_phash's value.
    value: str
    # Hashes of the seven non-upright dihedral transforms, keyed by ORIENTATION_VARIANTS name.
    variants: dict[str, str]


def compute_orientation_phashes(path: Path) -> OrientationHashes:
    """pHash of the upright image and of its rotated and mirrored copies (one decode)."""
    with Image.open(path) as image:
        image.seek(0)
        image.draft("L", (HASH_SIZE * 32, HASH_SIZE * 32))
        upright = ImageOps.exif_transpose(image)
        bases = {False: upright, True: upright.transpose(Image.Transpose.FLIP_LEFT_RIGHT)}
        value = str(imagehash.phash(upright, hash_size=HASH_SIZE))
        variants = {}
        for name, degrees, mirrored in ORIENTATION_VARIANTS:
            transformed = bases[mirrored]
            if degrees:
                transformed = transformed.transpose(_ROTATIONS[degrees])
            variants[name] = str(imagehash.phash(transformed, hash_size=HASH_SIZE))
    return OrientationHashes(value, variants)


def orientation_of(name: str | None) -> tuple[int, bool]:
    """(rotation degrees counter-clockwise, mirrored) for a variant name; upright for None."""
    for variant, degrees, mirrored in ORIENTATION_VARIANTS:
        if variant == name:
            return degrees, mirrored
    return 0, False


def hamming_distance(first: str, second: str) -> int:
    return (int(first, 16) ^ int(second, 16)).bit_count()


def imagehash_version() -> str:
    return f"{version('ImageHash')} (Pillow {PIL.__version__})"
