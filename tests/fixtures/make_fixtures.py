"""Deterministic test images.

The test suite builds these in a temporary folder. To write them somewhere for manual testing:

    python -m tests.fixtures.make_fixtures samples/generated
"""

import random
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass, fields
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FIXTURES_DIR = Path(__file__).parent
C2PA_SAMPLE = FIXTURES_DIR / "c2pa" / "adobe-20220124-C.jpg"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONT_PATH = FONT_DIR / "DejaVuSans.ttf"
OCR_TEXT = "VESTIGO EVIDENCE SAMPLE 2026"

# Drawn into the scene video's first and last scenes (keyframe OCR tests).
VIDEO_TEXT_SCENE_1 = "SCENE ONE"
VIDEO_TEXT_SCENE_3 = "SCENE THREE"
# The scene video: three 3-second scenes with cuts at 3.0 s and 6.0 s, 640x360, with audio.
VIDEO_SCENE_CUTS = (3.0, 6.0)
VIDEO_SCENES_DURATION = 9.0

# Words drawn into the OCR fixtures, used by tests to count how many were recovered.
OCR_SCREENSHOT_WORDS = (
    "Case", "Dashboard", "Artifact", "uploaded", "Status", "analysis", "complete",
    "Reviewer", "assigned", "Download", "Report",
)  # fmt: skip
OCR_LOW_RES_TEXT = "INVOICE 4821 PAID IN FULL"
OCR_NOISY_TEXT = "FIELD NOTES 17 MARCH"

# The C2PA JUMBF type identifier: "c2pa" followed by the standard ISO suffix.
C2PA_JUMBF_TYPE = b"c2pa" + bytes.fromhex("00110010800000aa00389b71")


@dataclass(frozen=True)
class FixtureSet:
    jpeg: Path
    png: Path
    webp: Path
    tiff: Path
    with_metadata: Path
    corrupt_exif: Path
    near_duplicate: Path
    edited: Path
    oriented: Path
    unrelated: Path
    ocr_text: Path
    ocr_screenshot: Path
    ocr_low_res: Path
    ocr_noisy: Path
    blank: Path
    invalid_c2pa: Path
    c2pa: Path
    gif: Path
    html_named_jpg: Path
    truncated_jpeg: Path
    oversized_dimensions: Path
    bomb_dimensions: Path
    video_scenes: Path
    video_frame_jpg: Path
    video_static: Path
    video_webm: Path
    video_mkv: Path
    video_mov: Path
    video_rotated: Path
    video_mirrored: Path
    video_no_audio: Path
    audio_only_mp4: Path
    truncated_mp4: Path
    html_named_mp4: Path


def textured_image(seed: int, size: tuple[int, int] = (640, 480)) -> Image.Image:
    """A gradient with random shapes: enough structure for perceptual hashing to be meaningful."""
    rng = random.Random(seed)
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    top = [rng.randrange(256) for _ in range(3)]
    bottom = [rng.randrange(256) for _ in range(3)]
    for y in range(height):
        t = y / (height - 1)
        draw.line(
            [(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom, strict=True))
        )
    for _ in range(25):
        x0, y0 = rng.randrange(width), rng.randrange(height)
        x1, y1 = x0 + rng.randrange(20, width // 2), y0 + rng.randrange(20, height // 2)
        color = tuple(rng.randrange(256) for _ in range(3))
        shape = draw.rectangle if rng.random() < 0.5 else draw.ellipse
        shape([x0, y0, x1, y1], fill=color)
    return image


def png_with_dimensions(width: int, height: int) -> bytes:
    """A tiny PNG whose header declares the given size (for pixel-limit tests)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 1, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00" * 64))
        + chunk(b"IEND", b"")
    )


def insert_jpeg_segment(jpeg: bytes, marker: int, payload: bytes) -> bytes:
    """Insert an APPn segment directly after the SOI marker."""
    assert jpeg[:2] == b"\xff\xd8"
    return jpeg[:2] + bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload + jpeg[2:]


def c2pa_jumbf_box() -> bytes:
    """A minimal JUMBF superbox carrying the C2PA type and label (structure only, no manifest)."""
    jumd = b"jumd" + C2PA_JUMBF_TYPE + b"\x03" + b"c2pa\x00"
    jumd_box = struct.pack(">I", len(jumd) + 4) + jumd
    return struct.pack(">I", len(jumd_box) + 8) + b"jumb" + jumd_box


def png_with_chunk(png: bytes, kind: bytes, data: bytes) -> bytes:
    """Insert a chunk before IEND."""
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    chunk = struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)
    iend = png.rindex(b"IEND") - 4
    return png[:iend] + chunk + png[iend:]


def webp_with_chunk(webp: bytes, kind: bytes, data: bytes) -> bytes:
    """Append a RIFF chunk and fix the RIFF size."""
    chunk = kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")
    body = webp[8:] + chunk
    return b"RIFF" + struct.pack("<I", len(body)) + body


def tiff_with_tag(tag: int, data: bytes) -> bytes:
    """A minimal little-endian TIFF whose only IFD entry is an UNDEFINED tag holding `data`."""
    ifd_offset = 8
    data_offset = ifd_offset + 2 + 12 + 4
    ifd = struct.pack("<H", 1) + struct.pack("<HHII", tag, 7, len(data), data_offset) + struct.pack("<I", 0)
    return b"II*\x00" + struct.pack("<I", ifd_offset) + ifd + data


def corrupt_exif_payload() -> bytes:
    # A TIFF header whose IFD0 claims 65535 entries, far more than the segment holds.
    return b"Exif\x00\x00" + b"II*\x00" + struct.pack("<I", 8) + struct.pack("<H", 0xFFFF) + b"\x00" * 16


def invalid_c2pa_payload() -> bytes:
    # A JUMBF description box labelled "c2pa" inside a superbox that claims more bytes than exist.
    label = b"c2pa\x00"
    jumd = b"jumd" + C2PA_JUMBF_TYPE + b"\x03" + label
    jumd_box = struct.pack(">I", len(jumd) + 4) + jumd
    superbox = struct.pack(">I", 0x00FFFFFF) + b"jumb" + jumd_box + b"\xde\xad\xbe\xef" * 4
    return b"JP" + struct.pack(">H", 1) + struct.pack(">I", 1) + superbox


def write_metadata(path: Path) -> None:
    subprocess.run(
        [
            "exiftool",
            "-q",
            "-overwrite_original",
            "-EXIF:Make=VestigoTestCam",
            "-EXIF:Model=Fixture Model 1",
            "-EXIF:DateTimeOriginal=2026:01:15 10:30:00",
            "-EXIF:Software=Vestigo fixture generator",
            "-EXIF:GPSLatitude=51.5",
            "-EXIF:GPSLatitudeRef=N",
            "-EXIF:GPSLongitude=0.12",
            "-EXIF:GPSLongitudeRef=W",
            "-XMP-dc:Title=Fixture title",
            "-XMP-dc:Creator=Fixture Author",
            "-IPTC:Keywords=fixture",
            "-IPTC:City=Testville",
            str(path),
        ],
        check=True,
    )


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def screenshot_image() -> Image.Image:
    """An app-window screenshot: small UI text, a dark title bar, and a button with white text."""
    image = Image.new("RGB", (900, 360), (243, 244, 246))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, 900, 48], fill=(31, 41, 55))
    draw.text((20, 14), "Case Dashboard", fill="white", font=font("DejaVuSans-Bold.ttf", 18))
    body = font("DejaVuSans.ttf", 15)
    draw.text((24, 80), "Artifact uploaded at 10:42", fill=(55, 65, 81), font=body)
    draw.text((24, 112), "Status: analysis complete", fill=(55, 65, 81), font=body)
    draw.text((24, 144), "Reviewer assigned: none", fill=(107, 114, 128), font=body)
    draw.line([24, 180, 876, 180], fill=(209, 213, 219), width=1)
    draw.rounded_rectangle([24, 210, 224, 250], radius=6, fill=(37, 99, 235))
    draw.text((46, 220), "Download Report", fill="white", font=font("DejaVuSans-Bold.ttf", 15))
    return image


def low_res_text_image() -> Image.Image:
    """8 px text in a 150x20 image, as in a thumbnail or a small crop."""
    image = Image.new("RGB", (150, 20), "white")
    ImageDraw.Draw(image).text((4, 6), OCR_LOW_RES_TEXT, fill=(20, 20, 20), font=font("DejaVuSans.ttf", 8))
    return image


def noisy_text_image() -> Image.Image:
    """Stylised, low-contrast text on an uneven background, with speckle noise and slight blur."""
    width, height = 900, 220
    image = Image.new("L", (width, height))
    image.putdata([150 + (x * 60) // width - (y * 30) // height for y in range(height) for x in range(width)])
    draw = ImageDraw.Draw(image)
    draw.text((40, 70), OCR_NOISY_TEXT, fill=95, font=font("DejaVuSansMono-BoldOblique.ttf", 60))
    rng = random.Random(7)
    pixels = image.load()
    for _ in range(width * height // 25):
        x, y = rng.randrange(width), rng.randrange(height)
        pixels[x, y] = rng.choice((40, 230))
    return image.filter(ImageFilter.GaussianBlur(1.2)).convert("RGB")


def ffmpeg(*args: str | Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def build_video_fixtures(path) -> dict[str, Path]:
    """Deterministic test videos, generated from ffmpeg lavfi sources (no committed binaries)."""
    draw = f"drawtext=fontfile={FONT_PATH}:text='{{text}}':fontsize=56:fontcolor={{color}}:x=40:y=120"
    scenes = path("scenes.mp4")
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=640x360:d=3",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=640x360:d=3",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=640x360:d=3",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=9",
        "-filter_complex",
        f"[0:v]{draw.format(text=VIDEO_TEXT_SCENE_1, color='white')},format=yuv420p[v0];"
        f"[1:v]format=yuv420p[v1];"
        f"[2:v]{draw.format(text=VIDEO_TEXT_SCENE_3, color='yellow')},format=yuv420p[v2];"
        "[v0][v1][v2]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-shortest",
        scenes,
    )
    # A re-encoded, downscaled copy: the duplicate-search test case. WebM requires Opus/Vorbis audio.
    ffmpeg(
        "-i",
        scenes,
        "-vf",
        "scale=320:-2",
        "-c:v",
        "libvpx-vp9",
        "-crf",
        "35",
        "-b:v",
        "0",
        "-deadline",
        "realtime",
        "-cpu-used",
        "8",
        "-c:a",
        "libopus",
        path("recoded.webm"),
    )
    ffmpeg("-i", scenes, "-c", "copy", path("scenes.mkv"))
    ffmpeg("-i", scenes, "-c", "copy", path("scenes.mov"))
    ffmpeg("-display_rotation", "90", "-i", scenes, "-c", "copy", path("rotated.mp4"))
    # A left-right mirrored re-encode: the mirrored duplicate-search case (D19).
    ffmpeg(
        "-i",
        scenes,
        "-vf",
        "hflip",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "30",
        "-c:a",
        "copy",
        path("mirrored.mp4"),
    )
    ffmpeg("-f", "lavfi", "-i", "color=c=green:s=320x240:d=4", "-c:v", "libx264", path("static.mp4"))
    ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=320x240:d=2", "-c:v", "libx264", path("no_audio.mp4"))
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac", path("audio_only.mp4"))
    # A still image taken from the video, for cross-media duplicate tests (M3-4).
    ffmpeg("-ss", "1.0", "-i", scenes, "-frames:v", "1", "-q:v", "2", path("frame_from_video.jpg"))
    path("truncated.mp4").write_bytes(scenes.read_bytes()[:400])
    path("page.mp4").write_bytes(b"<!doctype html><html><body>not a video</body></html>")
    return {
        "video_frame_jpg": path("frame_from_video.jpg"),
        "video_scenes": scenes,
        "video_static": path("static.mp4"),
        "video_webm": path("recoded.webm"),
        "video_mkv": path("scenes.mkv"),
        "video_mov": path("scenes.mov"),
        "video_rotated": path("rotated.mp4"),
        "video_mirrored": path("mirrored.mp4"),
        "video_no_audio": path("no_audio.mp4"),
        "audio_only_mp4": path("audio_only.mp4"),
        "truncated_mp4": path("truncated.mp4"),
        "html_named_mp4": path("page.mp4"),
    }


def build_fixtures(target: Path) -> FixtureSet:
    target.mkdir(parents=True, exist_ok=True)
    base = textured_image(seed=1)

    def path(name: str) -> Path:
        return target / name

    base.save(path("base.jpg"), quality=92)
    base.save(path("base.png"))
    base.save(path("base.webp"), quality=90)
    base.save(path("base.tiff"))

    base.save(path("with_metadata.jpg"), quality=92)
    write_metadata(path("with_metadata.jpg"))

    jpeg_bytes = path("base.jpg").read_bytes()
    path("corrupt_exif.jpg").write_bytes(insert_jpeg_segment(jpeg_bytes, 0xE1, corrupt_exif_payload()))
    path("invalid_c2pa.jpg").write_bytes(insert_jpeg_segment(jpeg_bytes, 0xEB, invalid_c2pa_payload()))

    base.resize((320, 240), Image.Resampling.LANCZOS).save(path("near_duplicate.jpg"), quality=60)

    # A small white box, like a redaction: visually close to the base image but not identical.
    edited = base.copy()
    ImageDraw.Draw(edited).rectangle([20, 20, 80, 60], fill="white")
    edited.save(path("edited.jpg"), quality=92)

    # Pixels stored rotated 90° counter-clockwise, with EXIF orientation 6 telling viewers to
    # rotate them back. Displayed upright, it matches the base image.
    exif = Image.Exif()
    exif[0x0112] = 6
    base.rotate(90, expand=True).save(path("oriented.jpg"), quality=92, exif=exif)

    textured_image(seed=99).save(path("unrelated.png"))

    text_image = Image.new("RGB", (1200, 200), "white")
    font = ImageFont.truetype(str(FONT_PATH), 56)
    ImageDraw.Draw(text_image).text((40, 60), OCR_TEXT, fill="black", font=font)
    text_image.save(path("ocr_text.png"))
    screenshot_image().save(path("ocr_screenshot.png"))
    low_res_text_image().save(path("ocr_low_res.png"))
    noisy_text_image().save(path("ocr_noisy.png"))

    Image.new("RGB", (400, 300), "white").save(path("blank.png"))
    Image.new("RGB", (32, 32), "red").save(path("animation.gif"))
    path("not_really.jpg").write_bytes(b"<!doctype html><html><body>not an image</body></html>")
    path("truncated.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 64)
    path("oversized.png").write_bytes(png_with_dimensions(11_000, 10_000))
    path("bomb.png").write_bytes(png_with_dimensions(20_000, 20_000))

    videos = build_video_fixtures(path)

    return FixtureSet(
        **videos,
        jpeg=path("base.jpg"),
        png=path("base.png"),
        webp=path("base.webp"),
        tiff=path("base.tiff"),
        with_metadata=path("with_metadata.jpg"),
        corrupt_exif=path("corrupt_exif.jpg"),
        near_duplicate=path("near_duplicate.jpg"),
        edited=path("edited.jpg"),
        oriented=path("oriented.jpg"),
        unrelated=path("unrelated.png"),
        ocr_text=path("ocr_text.png"),
        ocr_screenshot=path("ocr_screenshot.png"),
        ocr_low_res=path("ocr_low_res.png"),
        ocr_noisy=path("ocr_noisy.png"),
        blank=path("blank.png"),
        invalid_c2pa=path("invalid_c2pa.jpg"),
        c2pa=C2PA_SAMPLE,
        gif=path("animation.gif"),
        html_named_jpg=path("not_really.jpg"),
        truncated_jpeg=path("truncated.jpg"),
        oversized_dimensions=path("oversized.png"),
        bomb_dimensions=path("bomb.png"),
    )


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/generated")
    built = build_fixtures(out)
    for field in fields(built):
        print(f"{field.name:22} {getattr(built, field.name)}")
