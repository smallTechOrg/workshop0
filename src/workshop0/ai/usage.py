"""The only writer of network-AI spend (spec/agent.md §Shared client).

Interface stub laid down by the Phase-11 shared scaffold; filled by slice S5 (ai-client).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from src.workshop0.ai.anthropic_client import LLMResult
    from src.workshop0.db.models import AiUsage


def record_usage(
    session: Session,
    result: LLMResult,
    *,
    purpose: str,
    cv_document_id: int | None = None,
    opportunity_id: int | None = None,
) -> AiUsage:
    """Write one `ai_usage` row (`workshop_id` null) and emit INFO `ai.<purpose>`."""
    raise NotImplementedError
