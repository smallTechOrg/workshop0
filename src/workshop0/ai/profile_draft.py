"""Profile drafter: CV text -> guarded ProfileInput pre-fill (spec/agent.md §Profile drafter).

Interface stub laid down by the Phase-11 shared scaffold; filled by slice S6 (profile-drafter).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.workshop0.ai.anthropic_client import LLMResult


@dataclass(frozen=True)
class TopicRef:
    slug: str
    name: str
    category: str


@dataclass(frozen=True)
class DraftResult:
    draft: dict[str, Any]
    autofilled_fields: list[str]
    llm: LLMResult


class DraftRejected(Exception):
    """The model's output failed the guardrails; carries the spent call for usage recording."""

    def __init__(self, llm: LLMResult, message: str = "draft rejected by guardrails") -> None:
        super().__init__(message)
        self.llm = llm


def draft_profile(cv_text: str, topics: list[TopicRef]) -> DraftResult:
    """Pure: one LLM call + guardrails, no DB. Raises LLMUnavailable / LLMError / DraftRejected."""
    raise NotImplementedError


def run_profile_draft(cv_document_id: int) -> None:
    """BackgroundTask wrapper: loads the CV document, drafts, stores the result and usage."""
    raise NotImplementedError
