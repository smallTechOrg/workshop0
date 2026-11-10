"""`/api/admin/opportunities/{id}/applications...` - the applicant pipeline (api.md §Phase 12)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from src.workshop0.api._common import ok, request_base_url
from src.workshop0.auth.deps import AdminActor, require_admin
from src.workshop0.db.session import get_session
from src.workshop0.email import sender
from src.workshop0.security import require_admin_key
from src.workshop0.services import applications
from src.workshop0.services.opportunities import NOT_FOUND_MESSAGE, parse_path_id

router = APIRouter(prefix="/api/admin/opportunities", dependencies=[Depends(require_admin_key)])


@router.get("/{opportunity_id}/applications")
def list_applications(
    opportunity_id: str,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> dict:
    oid = parse_path_id(opportunity_id, NOT_FOUND_MESSAGE)
    return ok(
        applications.list_pipeline(
            session, oid, status=status or None, page=page, page_size=page_size
        )
    )


@router.post("/{opportunity_id}/applications/status")
def bulk_status(
    opportunity_id: str,
    body: applications.BulkStatusBody,
    request: Request,
    background: BackgroundTasks,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    oid = parse_path_id(opportunity_id, NOT_FOUND_MESSAGE)
    result = applications.bulk_status(
        session, oid, body, base_url=request_base_url(request), by=actor.by
    )
    session.commit()
    if result["emails_queued"]:
        sender.schedule_drain(background)
    return ok(result)


@router.get("/{opportunity_id}/applications.csv")
def applications_csv(opportunity_id: str, session: Session = Depends(get_session)) -> Response:
    oid = parse_path_id(opportunity_id, NOT_FOUND_MESSAGE)
    filename, text = applications.export_csv(session, oid)
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
