from fastapi import APIRouter

from app.api.deps import Services
from app.schemas.library import LibrarySummary
from app.services import library

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/summary", response_model=LibrarySummary)
def get_library_summary(services: Services) -> LibrarySummary:
    """Duplicate-library index status and storage usage (M2-7)."""
    with services.db.reader() as session:
        return library.library_summary(session)
