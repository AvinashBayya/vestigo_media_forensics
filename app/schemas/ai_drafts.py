"""AI draft schemas (Pass 1, D24). Drafts are never evidence; every surface labels them."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.ai.runtime import AI_LABEL

DRAFTS_NOTICE = (
    f"{AI_LABEL} These fields were proposed by a local model reading material Vestigo already "
    "holds. They are not evidence, nothing in them is verified, and nothing is written back over "
    "metadata or evidence. A confidence value appears only where the model supplied one."
)

DraftSource = Literal["ocr_text", "analyst_notes", "metadata", "transcript"]
FieldAction = Literal["accepted", "edited", "rejected"]


class DraftGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: DraftSource
    # The shape the model must fill: these field names and no others.
    fields: list[str] = Field(min_length=1, max_length=25)


class DraftField(BaseModel):
    name: str
    # The model's own value, kept even after the analyst edits or rejects it.
    value: str
    # Only ever the model's own estimate; Vestigo never calculates one.
    confidence: float | None = None
    status: Literal["proposed", "accepted", "edited", "rejected"] = "proposed"
    # The analyst's replacement text, when they edited the field.
    edited_value: str | None = None


class FieldDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=100)
    action: FieldAction
    # Required for an edit, refused otherwise.
    value: str | None = Field(default=None, max_length=10_000)

    def model_post_init(self, _context: object) -> None:
        if self.action == "edited" and not (self.value or "").strip():
            raise ValueError("An edited field needs the analyst's replacement value.")
        if self.action != "edited" and self.value is not None:
            raise ValueError("A value may only be given when editing a field.")


class AIDraftInfo(BaseModel):
    draft_id: str
    artifact_id: str
    kind: str
    source_kind: str
    source_evidence_id: str | None
    fields: list[DraftField]
    status: str
    # Model provenance: name, version, quantization, source_url, license, runtime, local_path.
    model: dict
    reasoning: str | None = None
    warnings: list[str] = []
    created_at: datetime
    updated_at: datetime | None


class AIDraftsResponse(BaseModel):
    artifact_id: str
    notice: str = DRAFTS_NOTICE
    label: str = AI_LABEL
    drafts: list[AIDraftInfo]
