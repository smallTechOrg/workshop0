"""Admin Opportunity Board surface — header `X-Admin-Key` (spec/api.md §Phase 10 Admin).

Thin HTTP layer: validation, status rules, audit and logging live in
services/opportunities.py and services/topics.py.
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.workshop0.api._common import ok, request_base_url
from src.workshop0.db.session import get_session
from src.workshop0.security import require_admin_key
from src.workshop0.services import opportunities, topics
from src.workshop0.services.opportunities import (
    NOT_FOUND_MESSAGE,
    OpportunityCreate,
    OpportunityPatch,
    parse_path_id,
)
from src.workshop0.services.topics import TopicCreate, TopicPatch

# Same text as services/topics.py::update_topic's 404 (that module is not this slice's).
TOPIC_NOT_FOUND_MESSAGE = "No topic matches this id."

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])


@router.get("/opportunities")
def list_opportunities(
    request: Request,
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    return ok(
        opportunities.list_admin(
            session,
            base_url=request_base_url(request),
            status=status or None,
            type_=type or None,
            q=q,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/opportunities")
def create_opportunity(
    body: OpportunityCreate, request: Request, session: Session = Depends(get_session)
) -> dict:
    created = opportunities.create_opportunity(session, body, base_url=request_base_url(request))
    return ok({"opportunity": created})


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(
    opportunity_id: str, request: Request, session: Session = Depends(get_session)
) -> dict:
    oid = parse_path_id(opportunity_id, NOT_FOUND_MESSAGE)
    return ok(opportunities.get_admin(session, oid, base_url=request_base_url(request)))


@router.patch("/opportunities/{opportunity_id}")
def update_opportunity(
    opportunity_id: str,
    body: OpportunityPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    oid = parse_path_id(opportunity_id, NOT_FOUND_MESSAGE)
    updated = opportunities.update_opportunity(
        session, oid, body, base_url=request_base_url(request)
    )
    return ok({"opportunity": updated})


@router.get("/topics")
def list_topics(session: Session = Depends(get_session)) -> dict:
    return ok({"topics": topics.list_admin_topics(session)})


@router.post("/topics")
def create_topic(body: TopicCreate, session: Session = Depends(get_session)) -> dict:
    return ok({"topic": topics.create_topic(session, body)})


@router.patch("/topics/{topic_id}")
def update_topic(
    topic_id: str, body: TopicPatch, session: Session = Depends(get_session)
) -> dict:
    tid = parse_path_id(topic_id, TOPIC_NOT_FOUND_MESSAGE)
    return ok({"topic": topics.update_topic(session, tid, body)})
