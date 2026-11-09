"""Admin opportunity paste-to-fill drafting — spec/api.md §Phase 11b.

`POST /api/admin/opportunity-draft` is a synchronous call into `ai/opportunity_draft.py`. It never
creates or modifies a listing; its only write is the `ai_usage` row.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.ai import anthropic_client
from src.workshop0.ai.opportunity_draft import PURPOSE, run_opportunity_draft
from src.workshop0.api._common import api_error, ok
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import Opportunity
from src.workshop0.db.session import get_session
from src.workshop0.security import require_admin_key
from src.workshop0.services import ratelimit

TEXT_MIN, TEXT_MAX = 40, 20000
RATE_LIMIT, RATE_WINDOW_S = 60, 3600  # global bucket `opportunity_draft`

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])


class OpportunityDraftRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    opportunity_id: int | None = None
    keep_partner_identity: bool = False

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not (TEXT_MIN <= len(trimmed) <= TEXT_MAX):
            raise ValueError(f"paste between {TEXT_MIN} and {TEXT_MAX} characters")
        return trimmed


@router.get("/opportunity-draft/config")
def draft_config() -> dict:
    return ok(
        {
            "available": anthropic_client.is_available(),
            "model": get_settings().workshop0_ai_network_model,
        }
    )


@router.post("/opportunity-draft")
def draft(body: OpportunityDraftRequest, session: Session = Depends(get_session)) -> dict:
    if body.opportunity_id is not None and (
        session.scalar(select(Opportunity.id).where(Opportunity.id == body.opportunity_id)) is None
    ):
        raise api_error("validation_error", "opportunity_id: no opportunity with this id", 422)
    ratelimit.enforce(session, PURPOSE, RATE_LIMIT, RATE_WINDOW_S)
    return ok(
        run_opportunity_draft(
            session,
            text=body.text,
            opportunity_id=body.opportunity_id,
            keep_partner_identity=body.keep_partner_identity,
        )
    )
