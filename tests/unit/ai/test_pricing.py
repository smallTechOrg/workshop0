"""Pricing math and the unknown-model rule (spec/agent.md §Shared client / §Testing)."""

from decimal import Decimal

from structlog.testing import capture_logs

from src.workshop0.ai import pricing
from src.workshop0.observability.logging import configure_logging


def test_sonnet_one_million_each_way():
    assert pricing.cost_usd("claude-sonnet-5-5", 1_000_000, 1_000_000) == Decimal("18.000000")


def test_haiku_one_million_each_way():
    assert pricing.cost_usd("claude-haiku-5-5", 1_000_000, 1_000_000) == Decimal("6.000000")


def test_small_counts_round_to_six_dp():
    # 123 * 3/M + 45 * 15/M = 0.000369 + 0.000675
    cost = pricing.cost_usd("claude-sonnet-5-5", 123, 45)
    assert cost == Decimal("0.001044")
    assert cost.as_tuple().exponent == -6


def test_half_micro_dollar_rounds_up():
    assert pricing.cost_usd("claude-haiku-5-5", 1, 0) == Decimal("0.000001")
    # one token at USD 0.50/Mtok = 0.0000005 -> ROUND_HALF_UP to 0.000001
    original = pricing.PRICING_USD_PER_MTOK.copy()
    try:
        pricing.PRICING_USD_PER_MTOK["half-model"] = (Decimal("0.50"), Decimal(0))
        assert pricing.cost_usd("half-model", 1, 0) == Decimal("0.000001")
    finally:
        pricing.PRICING_USD_PER_MTOK.clear()
        pricing.PRICING_USD_PER_MTOK.update(original)


def test_zero_tokens_cost_zero():
    assert pricing.cost_usd("claude-sonnet-5-5", 0, 0) == Decimal(0)


def test_unknown_model_costs_zero_and_warns_once():
    configure_logging("INFO")
    with capture_logs() as events:
        cost = pricing.cost_usd("claude-mystery-9", 5000, 700)
    assert cost == Decimal(0)
    warnings = [e for e in events if e["event"] == "ai.pricing_unknown"]
    assert len(warnings) == 1
    assert warnings[0]["log_level"] == "warning"
    assert warnings[0]["model"] == "claude-mystery-9"
    assert (warnings[0]["prompt_tokens"], warnings[0]["completion_tokens"]) == (5000, 700)


def test_known_model_does_not_warn():
    configure_logging("INFO")
    with capture_logs() as events:
        pricing.cost_usd("claude-haiku-5-5", 10, 10)
    assert not [e for e in events if e["event"] == "ai.pricing_unknown"]


def test_table_has_exactly_the_assumed_prices():
    assert pricing.PRICING_USD_PER_MTOK == {
        "claude-sonnet-5-5": (Decimal("3.00"), Decimal("15.00")),
        "claude-haiku-5-5": (Decimal("1.00"), Decimal("5.00")),
    }
