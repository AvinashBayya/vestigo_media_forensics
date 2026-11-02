from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class UTCDateTime(TypeDecorator[datetime]):
    """Stores timezone-aware datetimes as sortable ISO-8601 UTC text."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamps must be timezone-aware.")
        return value.astimezone(UTC).strftime(_TIMESTAMP_FORMAT)

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return datetime.strptime(value, _TIMESTAMP_FORMAT).replace(tzinfo=UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime()}
