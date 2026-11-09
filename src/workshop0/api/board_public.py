"""Public Opportunity Board surface — no auth (spec/api.md §Phase 10 Public surface).

Every payload here is built by an allow-list serializer in services/opportunities.py /
services/topics.py: the internal partner name and notes are unreachable from this module.
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.workshop0.api._common import ok, request_base_url, utcnow
from src.workshop0.db.session import get_session
from src.workshop0.services import opportunities
from src.workshop0.services.topics import list_public_topics

router = APIRouter(prefix="/api/public")


@router.get("/topics")
def public_topics(session: Session = Depends(get_session)) -> dict:
    return ok({"topics": list_public_topics(session, utcnow())})


@router.get("/opportunities")
def public_opportunities(
    request: Request,
    type: str | None = Query(default=None),
    topic: list[str] = Query(default=[]),
    sort: str = Query(default="newest"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    session: Session = Depends(get_session),
) -> dict:
    return ok(
        opportunities.list_public(
            session,
            base_url=request_base_url(request),
            type_=type or None,
            topic_slugs=[slug for slug in topic if slug],
            sort=sort or "newest",
            page=page,
            page_size=page_size,
        )
    )


@router.get("/opportunities/{opportunity_id}")
def public_opportunity(
    opportunity_id: str, request: Request, session: Session = Depends(get_session)
) -> dict:
    # Non-integer / out-of-range ids are simply "not available" (never a 422 or a 500).
    oid = opportunities.parse_path_id(opportunity_id, opportunities.NOT_AVAILABLE_MESSAGE)
    detail = opportunities.get_public(session, oid, base_url=request_base_url(request))
    return ok({"opportunity": detail})
