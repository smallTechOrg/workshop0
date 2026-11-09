"""Anthropic list prices for cost accounting (spec/agent.md §Shared client).

Assumed values — the operator confirms them against Anthropic's pricing page.
Interface stub laid down by the Phase-11 shared scaffold; filled by slice S5 (ai-client).
"""

from __future__ import annotations

from decimal import Decimal

# {model_id: (input USD per million tokens, output USD per million tokens)}
PRICING_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5-5": (Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-5-5": (Decimal("1.00"), Decimal("5.00")),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Cost to 6 dp; an unknown model costs 0 and logs WARNING `ai.pricing_unknown`."""
    raise NotImplementedError
