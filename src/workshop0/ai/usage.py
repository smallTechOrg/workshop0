"""The only writer of network-AI spend (spec/agent.md §Shared client)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy.orm import Session

from src.workshop0.db.models import AiUsage

if TYPE_CHECKING:
    from src.workshop0.ai.anthropic_client import LLMResult

log = structlog.get_logger("workshop0")


def record_usage(
    session: Session,
    result: LLMResult,
    *,
    purpose: str,
    cv_document_id: int | None = None,
    opportunity_id: int | None = None,
) -> AiUsage:
    """Write one `ai_usage` row (`workshop_id` null) and emit INFO `ai.<purpose>`.

    The row is flushed (it has an id) but not committed — the caller owns the transaction.
    """
    row = AiUsage(
        workshop_id=None,
        cv_document_id=cv_document_id,
        opportunity_id=opportunity_id,
        purpose=purpose,
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )
    session.add(row)
    session.flush()
    log.info(
        f"ai.{purpose}",
        ai_usage_id=row.id,
        model=result.model,
        latency_ms=result.latency_ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=str(result.cost_usd),
        cv_document_id=cv_document_id,
        opportunity_id=opportunity_id,
    )
    return row
