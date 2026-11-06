"""Chain-of-custody report (M4B): what Vestigo recorded on this machine since upload."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

CUSTODY_NOTICE = (
    "This chain of custody lists what Vestigo recorded on this machine since the file was "
    "uploaded. It is not a legal chain of custody, it says nothing about the file's history "
    "before upload, and no event is ever inferred: evidence-package exports and duplicate-library "
    "changes made before schema revision 0005 were not recorded anywhere and therefore do not "
    "appear. Derived files written before that revision have no recorded source."
)


class CustodyTimelineEvent(BaseModel):
    """One recorded action. `source_table` names where the fact lives; nothing is inferred."""

    type: str
    at: datetime
    source_table: str
    detail: dict[str, Any]


class CustodyDerivedFile(BaseModel):
    """One derived file with its recorded lineage. A null source_kind means the row was written
    before revision 0005 and its source was not recorded - never guessed."""

    derived_file_id: str
    job_id: str
    stage: str
    kind: str
    filename: str
    sha256: str
    size_bytes: int
    created_at: datetime
    source_kind: str | None
    source_derived_file_id: str | None


class CustodyReport(BaseModel):
    artifact_id: str
    notice: str = CUSTODY_NOTICE
    events: list[CustodyTimelineEvent]
    derived_files: list[CustodyDerivedFile]
