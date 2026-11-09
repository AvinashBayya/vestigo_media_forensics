"""The integration surface (Pass 3, D26).

Every route here is a GET. There is deliberately no write operation of any kind, so an external
system reading Vestigo can never create, change, re-classify, or delete anything it holds - the
"no direct database writes by external integrations" rule is enforced by the absence of the
endpoints rather than by a permission check that could be misconfigured.

The surface is disabled by default and returns 409 with a clear reason until the analyst enables it.
"""

from fastapi import APIRouter

from app import __version__
from app.api.deps import Services
from app.core import migrations
from app.core.errors import AppError
from app.schemas.common import ErrorCode
from app.schemas.evidence import EvidenceReport
from app.schemas.integration import (
    INTEGRATION_VERSION,
    IntegrationEvidence,
    IntegrationVersion,
)
from app.services import app_settings, cases, custody, reports

router = APIRouter(prefix="/integration", tags=["integration"])

READ_ONLY_ENDPOINTS = [
    "GET /api/v1/integration/version",
    "GET /api/v1/integration/artifacts/{artifact_id}/evidence",
]

DISABLED_REASON = (
    "The integration API is turned off. Enable it in Settings to let another system read evidence "
    "from this machine; it is read-only and can never write anything."
)


def _require_enabled(services: Services) -> None:
    editable = app_settings.get_settings_response(services).editable
    if not editable.integration_api_enabled:
        raise AppError(409, ErrorCode.INTEGRATION_DISABLED, DISABLED_REASON, {})


@router.get("/version", response_model=IntegrationVersion)
def get_integration_version(services: Services) -> IntegrationVersion:
    """The integration contract's version and what it offers. Readable whether or not it is on, so
    an integrator can discover that it exists and that it is currently disabled."""
    editable = app_settings.get_settings_response(services).editable
    with services.db.reader() as session:
        revision = migrations.current_revision(session.connection())
    return IntegrationVersion(
        integration_version=INTEGRATION_VERSION,
        report_schema_version=EvidenceReport.model_fields["schema_version"].default,
        app_version=__version__,
        schema_revision=revision,
        enabled=editable.integration_api_enabled,
        read_only_endpoints=list(READ_ONLY_ENDPOINTS),
    )


@router.get("/artifacts/{artifact_id}/evidence", response_model=IntegrationEvidence)
def get_integration_evidence(
    services: Services, artifact_id: str, job_id: str | None = None
) -> IntegrationEvidence:
    """One artifact's evidence report, its chain of custody, and the cases it belongs to, in one
    versioned envelope. Reading changes nothing: no custody event is written for a read, because
    Vestigo only records actions it can observe as changes to what it holds."""
    _require_enabled(services)
    report = reports.build_report(services.db, artifact_id, job_id)
    custody_report = custody.build_custody_report(services.db, artifact_id)
    with services.db.reader() as session:
        linked = cases.cases_for_artifact(session, artifact_id)
    return IntegrationEvidence(
        artifact_id=artifact_id,
        report=report.model_dump(mode="json"),
        custody=custody_report.model_dump(mode="json"),
        cases=linked,
    )
