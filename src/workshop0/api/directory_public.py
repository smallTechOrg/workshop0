"""Phase 13: public trainer directory API (no auth). spec/api.md §Public directory."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, ok, request_base_url
from src.workshop0.db.session import get_session
from src.workshop0.services import directory

router = APIRouter(prefix="/api/public/trainers", tags=["directory"])

NOT_AVAILABLE = "This trainer profile isn't available."


@router.get("")
def list_trainers(
    request: Request,
    topic: str | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=100000),
    session: Session = Depends(get_session),
) -> dict:
    return ok(directory.list_public(session, topic=topic, page=page, base_url=request_base_url(request)))


@router.get("/{slug}")
def get_trainer(slug: str, request: Request, session: Session = Depends(get_session)) -> dict:
    detail = directory.get_public(session, slug.lower(), base_url=request_base_url(request))
    if detail is None:
        raise api_error("not_found", NOT_AVAILABLE, 404)
    return ok(detail)
