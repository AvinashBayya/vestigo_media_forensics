"""Versioned integration contract (Pass 3, D26). Read-only by construction."""

from typing import Any

from pydantic import BaseModel

# The integration contract's own version, separate from the evidence report's schema_version.
INTEGRATION_VERSION = "1.0"

INTEGRATION_NOTICE = (
    "Read-only integration view. Vestigo exposes evidence for another system to read; the "
    "integration surface has no write operation of any kind, so an external system can never "
    "create, change, re-classify, or delete an artifact, an evidence record, a review state, or "
    "anything else Vestigo holds. It is disabled by default and must be enabled by the analyst."
)


class IntegrationVersion(BaseModel):
    integration_version: str = INTEGRATION_VERSION
    report_schema_version: str
    app_version: str
    schema_revision: str | None
    enabled: bool
    notice: str = INTEGRATION_NOTICE
    # Exactly what this surface offers. Every entry is a GET.
    read_only_endpoints: list[str] = []


class IntegrationEvidence(BaseModel):
    """One artifact, as another system may read it. A superset of the evidence report."""

    integration_version: str = INTEGRATION_VERSION
    notice: str = INTEGRATION_NOTICE
    artifact_id: str
    # The evidence report exactly as Vestigo serves it, including its own schema_version.
    report: dict[str, Any]
    # The chain of custody Vestigo recorded on this machine.
    custody: dict[str, Any]
    # Cases this artifact was put in: organisation, not evidence.
    cases: list[dict[str, str]] = []
