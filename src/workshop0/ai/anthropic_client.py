"""The one Anthropic client for network AI (spec/agent.md §Provider / §Shared client).

The only module in `src/` that constructs the SDK client; every request carries the
`anthropic-workspace-id` default header. Interface stub laid down by the Phase-11 shared
scaffold; filled by slice S5 (ai-client), which keeps these signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import anthropic
    import httpx

    from src.workshop0.config.settings import Settings


class LLMUnavailable(Exception):
    """Network AI is off (no key, or key without workspace id). Raised before any I/O."""


class LLMError(Exception):
    """A call failed; `cause` is `timeout` | `http_<status>` | `no_tool_output` | `truncated`."""

    def __init__(self, cause: str, message: str | None = None) -> None:
        super().__init__(message or cause)
        self.cause = cause


@dataclass(frozen=True)
class LLMResult:
    content: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    model: str


def is_available() -> bool:
    """True only when both the key and the workspace id are non-empty. Scaffold stub: False."""
    return False


def build_client(settings: Settings, http_client: httpx.Client | None = None) -> anthropic.Anthropic:
    """Construct the SDK client with the mandatory workspace header."""
    raise NotImplementedError


def get_client() -> anthropic.Anthropic:
    """Process-cached `build_client(get_settings())`."""
    raise NotImplementedError


def reset_client() -> None:
    """Drop the cached client (tests that override settings). Scaffold stub: no-op."""
    return None


def call_json(
    *,
    system: str,
    user: str,
    tool_name: str,
    input_schema: dict[str, Any],
    model: str,
    max_tokens: int,
    timeout_s: float,
) -> LLMResult:
    """One forced-tool `messages.create` used as structured output (one re-ask at most)."""
    raise NotImplementedError
