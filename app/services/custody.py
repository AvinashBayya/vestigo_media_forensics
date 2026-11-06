"""Custody events (M4B): record state-changing actions that leave no trace in other tables.

The chain of custody is what Vestigo recorded on this machine since upload — never an invented or
legal chain of custody. Upload, analysis jobs, evidence records, and review changes live in their
own tables; only exports, duplicate-library changes, and preview creation are recorded here. The
table is append-only (database triggers from revision 0005).
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core import ids
from app.core.clock import utcnow
from app.models import CustodyEvent

EXPORTED = "exported"
LIBRARY_CHANGED = "library_changed"
PREVIEW_CREATED = "preview_created"


def record_event(session: Session, artifact_id: str, event_type: str, detail: dict[str, Any]) -> CustodyEvent:
    event = CustodyEvent(
        id=ids.new_id(ids.CUSTODY_EVENT),
        artifact_id=artifact_id,
        event_type=event_type,
        detail=detail,
        created_at=utcnow(),
    )
    session.add(event)
    return event
