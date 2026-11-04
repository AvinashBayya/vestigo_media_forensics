"""Editable settings stored in SQLite, and the read-only environment view (M2-8).

A stored value that is no longer valid (e.g. after an upgrade) is ignored and the default is used.
Values are never logged.
"""

import logging
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import __version__
from app.core import migrations
from app.core.clock import utcnow
from app.core.config import Settings
from app.core.container import AppServices
from app.core.logging import get_logger, log_event
from app.models import AppSetting
from app.schemas.settings import EditableSettings, EnvironmentSettings, SettingsResponse, SettingsUpdate
from app.services.ocr import LANGUAGES

logger = get_logger("settings")


def editable_settings(session: Session) -> tuple[EditableSettings, Any]:
    stored = {row.key: row for row in session.scalars(select(AppSetting))}
    values: dict[str, Any] = {}
    for name, field in EditableSettings.model_fields.items():
        row = stored.get(name)
        if row is None:
            continue
        try:
            values[name] = TypeAdapter(field.annotation).validate_python(row.value)
        except ValidationError:
            log_event(logger, logging.WARNING, "settings.invalid_stored_value", status="ignored")
    updated_at = max((row.updated_at for row in stored.values()), default=None)
    return EditableSettings(**values), updated_at


def environment_settings(services: AppServices) -> EnvironmentSettings:
    settings: Settings = services.settings
    with services.db.reader() as session:
        revision = migrations.current_revision(session.connection())
    return EnvironmentSettings(
        data_dir=str(settings.data_dir.resolve()),
        max_upload_bytes=settings.max_upload_bytes,
        max_image_pixels=settings.max_image_pixels,
        duplicate_threshold=settings.phash_max_distance,
        max_video_upload_bytes=settings.max_video_upload_bytes,
        max_video_duration_seconds=settings.max_video_duration_seconds,
        max_video_pixels=settings.max_video_pixels,
        max_keyframes=settings.max_keyframes,
        scene_threshold=settings.scene_threshold,
        video_timeout_seconds=settings.video_timeout_seconds,
        max_audio_upload_bytes=settings.max_audio_upload_bytes,
        max_audio_duration_seconds=settings.max_audio_duration_seconds,
        job_mode=settings.job_mode,
        job_workers=settings.job_workers,
        tool_timeout_seconds=settings.tool_timeout_seconds,
        ocr_timeout_seconds=settings.ocr_timeout_seconds,
        ocr_languages=list(LANGUAGES),
        log_level=settings.log_level,
        app_version=__version__,
        schema_revision=revision,
    )


def get_settings_response(services: AppServices) -> SettingsResponse:
    with services.db.reader() as session:
        editable, updated_at = editable_settings(session)
    return SettingsResponse(
        editable=editable, environment=environment_settings(services), updated_at=updated_at
    )


def update_settings(services: AppServices, update: SettingsUpdate) -> SettingsResponse:
    changes = update.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if changes:
        now = utcnow()
        with services.db.writer() as session, session.begin():
            for key, value in changes.items():
                session.merge(AppSetting(key=key, value=value, updated_at=now))
    log_event(logger, logging.INFO, "settings.updated", count=len(changes))
    return get_settings_response(services)
