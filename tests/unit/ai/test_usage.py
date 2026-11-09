"""`record_usage` writes exactly one network `ai_usage` row and emits `ai.<purpose>`
(spec/agent.md §Shared client; data-model.md §ai_usage — changes). Runs on PostgreSQL."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from structlog.testing import capture_logs

from src.workshop0.ai.anthropic_client import LLMResult
from src.workshop0.ai.usage import record_usage
from src.workshop0.db.models import AiUsage, CvDocument
from src.workshop0.db.session import create_db_session
from src.workshop0.observability.logging import configure_logging

RESULT = LLMResult(
    content={"headline": "secret-ish CV-derived text"},
    prompt_tokens=1200,
    completion_tokens=340,
    cost_usd=Decimal("0.008700"),
    latency_ms=1834,
    model="claude-sonnet-5-5",
)


def _cv_document(make_user) -> int:
    user = make_user("usage-trainer@example.test")
    with create_db_session() as session:
        doc = CvDocument(user_id=user.id, source="text", sha256="0" * 64, text_extract="x" * 300)
        session.add(doc)
        session.flush()
        return doc.id


def test_profile_draft_usage_row_and_event(make_user):
    cv_id = _cv_document(make_user)
    configure_logging("INFO")

    with capture_logs() as events, create_db_session() as session:
        row = record_usage(session, RESULT, purpose="profile_draft", cv_document_id=cv_id)
        row_id = row.id

    with create_db_session() as session:
        stored = session.get(AiUsage, row_id)
        assert stored.workshop_id is None
        assert stored.help_request_id is None
        assert stored.cv_document_id == cv_id
        assert stored.opportunity_id is None
        assert stored.purpose == "profile_draft"
        assert stored.model == "claude-sonnet-5-5"
        assert (stored.prompt_tokens, stored.completion_tokens) == (1200, 340)
        assert Decimal(stored.cost_usd) == Decimal("0.008700")
        assert stored.latency_ms == 1834
        assert stored.created_at is not None
        assert session.scalar(select(func.count()).select_from(AiUsage)) == 1

    emitted = [e for e in events if e["event"] == "ai.profile_draft"]
    assert len(emitted) == 1
    event = emitted[0]
    assert event["log_level"] == "info"
    assert event["model"] == "claude-sonnet-5-5"
    assert (event["prompt_tokens"], event["completion_tokens"], event["latency_ms"]) == (1200, 340, 1834)
    assert event["cost_usd"] == "0.008700"
    assert event["cv_document_id"] == cv_id and event["opportunity_id"] is None
    assert "secret-ish" not in repr(events)  # the model output never reaches the log


def test_shortlist_usage_row_carries_opportunity_id(create_opportunity):
    opp = create_opportunity()
    configure_logging("INFO")

    with capture_logs() as events, create_db_session() as session:
        record_usage(session, RESULT, purpose="shortlist_rank", opportunity_id=opp["id"])

    with create_db_session() as session:
        stored = session.scalars(select(AiUsage)).one()
        assert (stored.purpose, stored.opportunity_id, stored.cv_document_id) == ("shortlist_rank", opp["id"], None)
        assert stored.workshop_id is None
    assert [e["event"] for e in events if e["event"].startswith("ai.")] == ["ai.shortlist_rank"]


def test_usage_without_any_link_is_still_a_network_row():
    with create_db_session() as session:
        record_usage(session, RESULT, purpose="profile_draft")

    with create_db_session() as session:
        network_spend = session.scalar(select(func.sum(AiUsage.cost_usd)).where(AiUsage.workshop_id.is_(None)))
        assert Decimal(network_spend) == Decimal("0.008700")


def test_unknown_cv_document_id_is_rejected_by_the_fk():
    with pytest.raises(IntegrityError), create_db_session() as session:
        record_usage(session, RESULT, purpose="profile_draft", cv_document_id=999_999)

    with create_db_session() as session:
        assert session.scalar(select(func.count()).select_from(AiUsage)) == 0
