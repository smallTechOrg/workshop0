"""Admin surface — header `X-Admin-Key` (see spec/api.md §Admin surface)."""

import structlog
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import iso_z, ok, request_base_url
from src.workshop0.auth.deps import AdminActor, require_admin
from src.workshop0.db.models import HelpRequest, Participant, Workshop
from src.workshop0.db.session import get_session
from src.workshop0.security import require_admin_key
from src.workshop0.services import tiein
from src.workshop0.services.workshops import (  # re-exported: the shared request models
    MilestoneIn,
    WorkshopCreate,
    create_workshop as create_workshop_record,
    workshop_urls,
)

__all__ = ["router", "MilestoneIn", "WorkshopCreate"]

log = structlog.get_logger("workshop0")

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])


@router.get("/workshops")
def list_workshops(request: Request, session: Session = Depends(get_session)) -> dict:
    base = request_base_url(request)
    workshops = list(
        session.scalars(select(Workshop).order_by(Workshop.created_at.desc(), Workshop.id.desc()))
    )
    participant_counts = dict(
        session.execute(
            select(Participant.workshop_id, func.count(Participant.id)).group_by(
                Participant.workshop_id
            )
        ).all()
    )
    open_help_counts = dict(
        session.execute(
            select(HelpRequest.workshop_id, func.count(HelpRequest.id))
            .where(HelpRequest.status == "open")
            .group_by(HelpRequest.workshop_id)
        ).all()
    )
    rows = [
        {
            "id": w.id,
            "name": w.name,
            "status": w.status,
            "participant_count": participant_counts.get(w.id, 0),
            "open_help_count": open_help_counts.get(w.id, 0),
            "created_at": iso_z(w.created_at),
            "join_slug": w.join_slug,
            **workshop_urls(base, w),
            "created_via": w.created_via,
            "creator_email": w.creator_email,
        }
        for w in workshops
    ]
    return ok({"workshops": rows})


@router.post("/workshops")
def create_workshop(
    body: WorkshopCreate, request: Request, session: Session = Depends(get_session)
) -> dict:
    return create_workshop_record(
        session,
        body,
        created_via="admin",
        creator_email=None,
        base_url=request_base_url(request),
    )


@router.get("/workshops/{workshop_id}/facilitators")
def get_facilitators(workshop_id: int, session: Session = Depends(get_session)) -> dict:
    return ok({"facilitators": tiein.list_for_workshop(session, workshop_id)})


@router.put("/workshops/{workshop_id}/facilitators")
def put_facilitators(
    workshop_id: int,
    body: dict = Body(...),
    session: Session = Depends(get_session),
    actor: AdminActor = Depends(require_admin),
) -> dict:
    items = body.get("facilitators")
    return ok({"facilitators": tiein.replace_for_workshop(session, workshop_id, items, by=actor.by)})


@router.post("/workshops/{workshop_id}/facilitators")
def post_facilitator(
    workshop_id: int,
    body: dict = Body(...),
    session: Session = Depends(get_session),
    actor: AdminActor = Depends(require_admin),
) -> dict:
    profile_id, role = body.get("profile_id"), body.get("role", "co")
    if isinstance(profile_id, bool) or not isinstance(profile_id, int):
        raise tiein._validation_error("profile_id: must be an integer")
    if role not in tiein.ROLES:
        raise tiein._validation_error("role: must be one of lead, co, ta")
    return ok({"facilitators": tiein.add_one(session, workshop_id, profile_id, role, by=actor.by)})
