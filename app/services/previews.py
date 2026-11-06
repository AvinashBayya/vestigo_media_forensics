"""On-demand playable previews (D19, amending M3-6's no-transcoding rule for viewing only).

One bounded ffmpeg run re-encodes a video the browser cannot play into an H.264/AAC MP4 capped at
PREVIEW_MAX_SIDE pixels. The result is a clearly-labelled viewing copy: it is not evidence, is not
part of the export package, and is deleted with the artifact. The original is only ever read.
"""

import hashlib
import logging

from app.core.clock import utcnow
from app.core.container import AppServices
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.core.tools import ToolError, run_tool
from app.models import PlayablePreview
from app.schemas.common import ErrorCode, MediaType
from app.services import custody
from app.services.artifacts import get_artifact
from app.services.errors import wrong_media_type
from app.services.validation import InvalidVideoError, probe_video

logger = get_logger("previews")

PREVIEW_MAX_SIDE = 1280


def preview_not_found(artifact_id: str) -> AppError:
    return AppError(
        404,
        ErrorCode.NOT_FOUND,
        "This artifact has no playable preview. Create one with POST "
        f"/api/v1/artifacts/{artifact_id}/preview.",
        {"artifact_id": artifact_id},
    )


def get_preview(services: AppServices, artifact_id: str) -> PlayablePreview:
    get_artifact(services.db, artifact_id)
    with services.db.reader() as session:
        preview = session.get(PlayablePreview, artifact_id)
    if preview is None:
        raise preview_not_found(artifact_id)
    return preview


def create_preview(services: AppServices, artifact_id: str) -> PlayablePreview:
    """Create the viewing copy, or return the existing one (the original never changes)."""
    artifact = get_artifact(services.db, artifact_id)
    if artifact.media_type != MediaType.VIDEO:
        raise wrong_media_type(artifact_id, artifact.media_type, "video")
    with services.db.reader() as session:
        existing = session.get(PlayablePreview, artifact_id)
    if existing is not None:
        return existing

    storage = services.storage
    source = storage.resolve(artifact.stored_path)
    temp = storage.new_temp_path(".mp4")
    args = [
        "-v",
        "error",
        "-y",
        "-i",
        source,
        "-vf",
        f"scale='min({PREVIEW_MAX_SIDE},iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        temp,
    ]
    try:
        completed = run_tool(
            services.tools.require("ffmpeg"), args, timeout=services.settings.video_timeout_seconds
        )
        if completed.returncode != 0 or not temp.is_file() or temp.stat().st_size == 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
            raise ToolError(
                f"ffmpeg exited with code {completed.returncode} "
                f"({stderr[-1] if stderr else 'no error output'})."
            )
        probe = probe_video(
            services.tools.require("ffprobe"), temp, services.settings.tool_timeout_seconds
        ).data
        video_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
        data = temp.read_bytes()
        stored_path = storage.store_preview(temp, artifact_id)
    except (ToolError, InvalidVideoError, OSError) as exc:
        temp.unlink(missing_ok=True)
        log_event(
            logger, logging.ERROR, "preview.failed", artifact_id=artifact_id, error_type=type(exc).__name__
        )
        raise AppError(
            500,
            ErrorCode.PREVIEW_FAILED,
            "The playable preview could not be created. The original file is unchanged.",
        ) from exc
    except BaseException:
        temp.unlink(missing_ok=True)
        raise

    preview = PlayablePreview(
        artifact_id=artifact_id,
        stored_path=stored_path,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        width=video_stream.get("width"),
        height=video_stream.get("height"),
        created_at=utcnow(),
    )
    with services.db.writer() as session, session.begin():
        current = session.get(PlayablePreview, artifact_id)
        if current is not None:
            # Another request finished first; keep its copy and drop ours.
            storage.purge(storage.resolve(stored_path).parent)
            return current
        session.add(preview)
        custody.record_event(
            session,
            artifact_id,
            custody.PREVIEW_CREATED,
            {
                "sha256": preview.sha256,
                "size_bytes": preview.size_bytes,
                "width": preview.width,
                "height": preview.height,
            },
        )
    log_event(logger, logging.INFO, "preview.created", artifact_id=artifact_id)
    return preview
