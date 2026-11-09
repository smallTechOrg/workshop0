"""Real Anthropic API, cheap fast model (spec/agent.md §Testing — Real API).

Uses the real ANTHROPIC_API_KEY + ANTHROPIC_WORKSPACE_ID from the gitignored `.env` via
settings. Values are never printed: assertions only check that they are absent from output.
"""

from __future__ import annotations

from decimal import Decimal

import anthropic
import pytest
from sqlalchemy import select
from structlog.testing import capture_logs

from src.workshop0.ai import anthropic_client, pricing
from src.workshop0.ai.anthropic_client import LLMError, LLMUnavailable
from src.workshop0.ai.usage import record_usage
from src.workshop0.config.settings import get_settings
from src.workshop0.db.models import AiUsage
from src.workshop0.db.session import create_db_session
from src.workshop0.observability.logging import configure_logging

PAIR_SCHEMA = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "description": "a colour name"},
        "count": {"type": "integer", "description": "a small whole number"},
    },
    "required": ["color", "count"],
}


@pytest.fixture(autouse=True)
def _real_credentials():
    settings = get_settings()
    if not (settings.anthropic_api_key.strip() and settings.anthropic_workspace_id.strip()):
        # agent.md §Testing: skip only when genuinely absent; the phase gate asserts presence first.
        pytest.skip("ANTHROPIC_API_KEY and ANTHROPIC_WORKSPACE_ID are required for real-API tests")
    anthropic_client.reset_client()
    yield
    anthropic_client.reset_client()


def _no_secrets_in(text: str) -> bool:
    settings = get_settings()
    return settings.anthropic_api_key not in text and settings.anthropic_workspace_id not in text


def _pair_call(**overrides):
    kwargs = {
        "system": "You fill in the requested fields. Be brief.",
        "user": "The colour is blue and the count is 3.",
        "tool_name": "submit_pair",
        "input_schema": PAIR_SCHEMA,
        "model": get_settings().workshop0_ai_network_fast_model,
        "max_tokens": 64,
        "timeout_s": 30,
    }
    kwargs.update(overrides)
    return anthropic_client.call_json(**kwargs)


def test_real_cheap_call_records_tokens_and_cost():
    settings = get_settings()
    assert anthropic_client.is_available() is True

    result = _pair_call()

    assert str(result.content["color"]).strip().lower() == "blue"
    assert int(result.content["count"]) == 3
    assert result.model == settings.workshop0_ai_network_fast_model
    assert result.prompt_tokens > 0 and result.completion_tokens > 0
    assert result.cost_usd > 0
    assert result.cost_usd == pricing.cost_usd(result.model, result.prompt_tokens, result.completion_tokens)
    assert result.latency_ms > 0

    configure_logging("INFO")
    with capture_logs() as events, create_db_session() as session:
        row_id = record_usage(session, result, purpose="profile_draft").id

    with create_db_session() as session:
        rows = session.scalars(select(AiUsage)).all()
        assert [r.id for r in rows] == [row_id]
        row = rows[0]
        assert row.workshop_id is None
        assert row.purpose == "profile_draft"
        assert row.model == settings.workshop0_ai_network_fast_model
        assert (row.prompt_tokens, row.completion_tokens) == (result.prompt_tokens, result.completion_tokens)
        assert Decimal(row.cost_usd) == result.cost_usd
        assert Decimal(row.cost_usd) > 0
    emitted = [e for e in events if e["event"] == "ai.profile_draft"]
    assert len(emitted) == 1 and emitted[0]["prompt_tokens"] == result.prompt_tokens
    assert _no_secrets_in(repr(events))


def test_real_sonnet_call_uses_structured_output_and_records_cost():
    """The configured drafting model (claude-sonnet-5-5) rejects forced tool use; the
    structured-output path must return schema-valid JSON and a priced result."""
    settings = get_settings()
    model = settings.workshop0_ai_network_model
    assert model == "claude-sonnet-5-5"

    result = _pair_call(model=model)

    assert set(result.content) == {"color", "count"}
    assert str(result.content["color"]).strip().lower() == "blue"
    assert isinstance(result.content["count"], int) and result.content["count"] == 3
    assert result.model == model
    assert result.prompt_tokens > 0 and result.completion_tokens > 0
    assert result.cost_usd > 0
    assert result.cost_usd == pricing.cost_usd(model, result.prompt_tokens, result.completion_tokens)

    with create_db_session() as session:
        record_usage(session, result, purpose="profile_draft")
    with create_db_session() as session:
        row = session.scalars(select(AiUsage)).one()
        assert row.model == model and Decimal(row.cost_usd) == result.cost_usd > 0


def test_real_sonnet_call_with_strict_mode_unsupported_keywords():
    """Edge case: a schema using keywords strict mode rejects (maxItems, minimum/maximum,
    nullable enum, nested objects without additionalProperties) is normalised, accepted by
    the API, and the result still honours the original bounds."""
    schema = {
        "type": "object",
        "properties": {
            "colors": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
            "count": {"type": "integer", "minimum": 0, "maximum": 10},
            "unit": {"type": ["string", "null"], "enum": ["day", "hour", None]},
            "meta": {"type": "object", "properties": {"note": {"type": ["string", "null"]}}, "required": ["note"]},
        },
        "required": ["colors", "count", "unit", "meta"],
    }

    result = _pair_call(
        model=get_settings().workshop0_ai_network_model,
        user="Colours: red, green. Count: 4. Billed per day. No note.",
        input_schema=schema,
        max_tokens=200,
    )

    assert 0 < len(result.content["colors"]) <= 2
    assert 0 <= result.content["count"] <= 10
    assert result.content["unit"] in ("day", "hour", None)
    assert set(result.content["meta"]) == {"note"}
    assert result.cost_usd > 0


def test_real_call_with_vague_user_text_still_returns_schema_shaped_output():
    """Edge case: next to no facts in the input — structured output still yields a dict."""
    result = _pair_call(user="(no details given)")

    assert isinstance(result.content, dict)
    assert result.prompt_tokens > 0 and result.cost_usd > 0


def test_real_call_with_unknown_model_maps_to_llm_error():
    """Error path: a non-existent model id is an API 4xx, surfaced as LLMError(http_<status>)."""
    with pytest.raises(LLMError) as excinfo:
        _pair_call(model="claude-does-not-exist-0-0")

    assert excinfo.value.cause in ("http_400", "http_404")
    assert excinfo.value.status in (400, 404)
    assert _no_secrets_in(f"{excinfo.value!s} {excinfo.value!r}")


def test_key_without_workspace_never_calls_the_api(network_ai_disabled):
    network_ai_disabled(which="workspace")

    assert anthropic_client.is_available() is False
    with pytest.raises(LLMUnavailable):
        _pair_call()
    with create_db_session() as session:
        assert session.scalars(select(AiUsage)).all() == []


def test_header_less_raw_client_gets_http_400():
    """Negative proof of the requirement: the key is not workspace-scoped, so a request
    WITHOUT `anthropic-workspace-id` is refused with 400. If this ever succeeds, the key's
    scoping changed on Anthropic's side — fail loudly so the spec is revisited."""
    raw = anthropic.Anthropic(api_key=get_settings().anthropic_api_key, max_retries=0, timeout=30)

    with pytest.raises(anthropic.BadRequestError) as excinfo:
        raw.messages.create(
            model=get_settings().workshop0_ai_network_fast_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )

    assert excinfo.value.status_code == 400
