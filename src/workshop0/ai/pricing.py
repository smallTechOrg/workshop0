"""Anthropic list prices for cost accounting (spec/agent.md §Shared client).

Assumed values — the operator confirms them against Anthropic's pricing page. A correction
is a one-line constant change; stored historic `ai_usage` rows are never rewritten.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import structlog

# {model_id: (input USD per million tokens, output USD per million tokens)}
PRICING_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-5-5": (Decimal("1.00"), Decimal("5.00")),
}

_MILLION = Decimal(1_000_000)
_SIX_DP = Decimal("0.000001")

log = structlog.get_logger("workshop0")


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Cost to 6 dp; an unknown model costs 0 and logs WARNING `ai.pricing_unknown`."""
    prices = PRICING_USD_PER_MTOK.get(model)
    if prices is None:
        log.warning(
            "ai.pricing_unknown",
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return Decimal(0).quantize(_SIX_DP)
    input_price, output_price = prices
    raw = (Decimal(max(input_tokens, 0)) * input_price + Decimal(max(output_tokens, 0)) * output_price) / _MILLION
    return raw.quantize(_SIX_DP, rounding=ROUND_HALF_UP)
