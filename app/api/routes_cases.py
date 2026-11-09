from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.cases import CaseCreate, CaseInfo, CasesResponse, CaseUpdate
from app.services import cases

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=CasesResponse)
def list_cases(services: Services) -> CasesResponse:
    """Every case, newest first (Pass 3). A case is organisation, never evidence."""
    return CasesResponse(cases=cases.list_cases(services))


@router.post("", response_model=CaseInfo, status_code=201)
def create_case(services: Services, payload: CaseCreate) -> CaseInfo:
    return cases.create_case(services, payload)


@router.get("/{case_id}", response_model=CaseInfo)
def get_case(services: Services, case_id: str) -> CaseInfo:
    return cases.get_case(services, case_id)


@router.patch("/{case_id}", response_model=CaseInfo)
def update_case(services: Services, case_id: str, update: CaseUpdate) -> CaseInfo:
    return cases.update_case(services, case_id, update)


@router.delete("/{case_id}", status_code=204)
def delete_case(services: Services, case_id: str) -> None:
    """Delete the case and its links. No artifact and no evidence is touched."""
    cases.delete_case(services, case_id)


@router.put("/{case_id}/artifacts/{artifact_id}", response_model=CaseInfo)
def link_artifact(services: Services, case_id: str, artifact_id: str) -> CaseInfo:
    """Put an artifact in this case. Recorded as a case_linked custody event on the artifact."""
    return cases.link_artifact(services, case_id, artifact_id)


@router.delete("/{case_id}/artifacts/{artifact_id}", response_model=CaseInfo)
def unlink_artifact(services: Services, case_id: str, artifact_id: str) -> CaseInfo:
    """Take an artifact out of this case. Recorded as a case_unlinked custody event."""
    return cases.unlink_artifact(services, case_id, artifact_id)
