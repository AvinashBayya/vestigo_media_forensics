"""Case schemas (Pass 3, D26). A case is organisation, never evidence."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

CASES_NOTICE = (
    "A case groups artifacts under a name you chose. It is organisation, not evidence: it carries "
    "no classification, asserts nothing about the artifacts in it, and deleting a case removes only "
    "the case and its links - never an artifact or its evidence."
)


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=10_000)


class CaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=10_000)


class CaseArtifactRef(BaseModel):
    artifact_id: str
    filename: str | None
    media_type: str | None
    added_at: datetime


class CaseInfo(BaseModel):
    case_id: str
    name: str
    notes: str
    artifact_count: int
    artifacts: list[CaseArtifactRef] = []
    created_at: datetime
    updated_at: datetime | None


class CasesResponse(BaseModel):
    notice: str = CASES_NOTICE
    cases: list[CaseInfo]
