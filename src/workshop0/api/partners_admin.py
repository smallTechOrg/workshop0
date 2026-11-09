"""Admin partner list surface — spec/api.md §Phase 11b.

Gate: `auth.deps.require_admin` (a valid `X-Admin-Key` or an admin session; CSRF header on
session mutations). Thin HTTP layer — validation, audit, mirror and logging are in
services/partners.py.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.workshop0.api._common import ok
from src.workshop0.auth.deps import AdminActor, require_admin
from src.workshop0.db.session import get_session
from src.workshop0.services import partners
from src.workshop0.services.opportunities import parse_path_id
from src.workshop0.services.partners import PartnerCreate, PartnerPatch

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


@router.get("/partners")
def list_partners(session: Session = Depends(get_session)) -> dict:
    return ok(partners.list_partners(session))


@router.post("/partners")
def create_partner(
    body: PartnerCreate,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    return ok(partners.create_partner(session, body, by=actor.by))


@router.patch("/partners/{partner_id}")
def patch_partner(
    partner_id: str,
    body: PartnerPatch,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    pid = parse_path_id(partner_id, partners.NOT_FOUND_MESSAGE)
    return ok(partners.update_partner(session, pid, body, by=actor.by))
