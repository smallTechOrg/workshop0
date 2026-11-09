"""The one Anthropic client for network AI (spec/agent.md §Provider / §Shared client).

The only module in `src/` that constructs the SDK client. Every request carries the
`anthropic-workspace-id` default header: the key is not workspace-scoped, and without the
header the API returns 400. Network AI is available only when the key AND the workspace id
are non-empty; otherwise `call_json` raises `LLMUnavailable` before any I/O.

Structured output uses `output_config` json_schema (strict mode), NOT a forced tool call:
claude-sonnet-5-5 rejects `tool_choice` `{"type": "tool"}` / `{"type": "any"}` with a 400.

Logs never carry the key, the workspace id, CV text or prompt bodies.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import anthropic

from src.workshop0.ai import pricing

if TYPE_CHECKING:
    # anthropic>=2 ships its own httpx fork and rejects plain `httpx.Client` objects.
    import httpx2

    from src.workshop0.config.settings import Settings

WORKSPACE_HEADER = "anthropic-workspace-id"
SDK_MAX_RETRIES = 1  # the SDK retries once on connection errors / 408 / 409 / 429 / 5xx
DEFAULT_TIMEOUT_S = 30.0  # client default; every call_json passes its own timeout_s
REASK_SUFFIX = "Respond only with a JSON object that matches the schema."


class LLMUnavailable(Exception):
    """Network AI is off (no key, or key without workspace id). Raised before any I/O."""


class LLMError(Exception):
    """A call failed; `cause` is `timeout` | `connection` (transport failure, no HTTP status) |
    `http_<status>` | `invalid_output` (no schema-valid JSON output after the re-ask)
    | `truncated` (`stop_reason == "max_tokens"`).

    `status` and `request_id` (Anthropic `request-id`) are set when the API answered, so the
    caller's `ai.call_failed` log can carry them.
    """

    def __init__(
        self,
        cause: str,
        message: str | None = None,
        *,
        status: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message or cause)
        self.cause = cause
        self.status = status
        self.request_id = request_id


@dataclass(frozen=True)
class LLMResult:
    content: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    latency_ms: int
    model: str


def _settings() -> Settings:
    from src.workshop0.config.settings import get_settings

    return get_settings()


def _credentials(settings: Settings) -> tuple[str, str]:
    return settings.anthropic_api_key.strip(), settings.anthropic_workspace_id.strip()


def is_available() -> bool:
    """True only when both the key and the workspace id are non-empty."""
    key, workspace = _credentials(_settings())
    return bool(key) and bool(workspace)


def build_client(settings: Settings, http_client: httpx2.Client | None = None) -> anthropic.Anthropic:
    """Construct the SDK client with the mandatory workspace header.

    `http_client` is injected by unit tests only (an `httpx2.Client` over a MockTransport).
    """
    key, workspace = _credentials(settings)
    return anthropic.Anthropic(
        api_key=key,
        default_headers={WORKSPACE_HEADER: workspace},
        max_retries=SDK_MAX_RETRIES,
        timeout=DEFAULT_TIMEOUT_S,
        http_client=http_client,
    )


_lock = threading.Lock()
_client: anthropic.Anthropic | None = None
_client_fingerprint: tuple[str, str] | None = None


def get_client() -> anthropic.Anthropic:
    """Process-cached `build_client(get_settings())`.

    The cache is keyed on the (key, workspace id) pair, so a settings swap (tests rebuild the
    settings singleton) can never reuse a client built from other credentials.
    """
    global _client, _client_fingerprint
    settings = _settings()
    fingerprint = _credentials(settings)
    with _lock:
        if _client is None or _client_fingerprint != fingerprint:
            _client = build_client(settings)
            _client_fingerprint = fingerprint
        return _client


def reset_client() -> None:
    """Drop the cached client (tests that override settings)."""
    global _client, _client_fingerprint
    with _lock:
        _client = None
        _client_fingerprint = None


# --------------------------------------------------------------------------- strict schema
#
# Structured outputs (`output_config.format = json_schema`) accept only a subset of JSON
# Schema, verified against the live API (claude-sonnet-5-5 / claude-haiku-5-5):
#   * every object MUST carry `additionalProperties: false` (a schema value is rejected);
#   * arrays reject `maxItems`, `uniqueItems`, and `minItems` other than 0/1;
#   * numbers/integers reject `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`,
#     `multipleOf`;
#   * strings accept only a fixed `format` set;
#   * an `enum` next to a list `type` (e.g. `["string", "null"]`) is rejected.
# `normalize_schema` rewrites a caller's schema into that subset; every constraint it strips is
# then enforced in Python against the ORIGINAL schema by `_conform` (arrays over `maxItems`
# are truncated, any other violation counts as invalid output and triggers the re-ask).

_STRIPPED_KEYWORDS = frozenset(
    {
        "maxItems",
        "uniqueItems",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minProperties",
        "maxProperties",
    }
)
_SUPPORTED_FORMATS = frozenset(
    {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}
)
_SCHEMA_MAPS = ("properties", "$defs", "definitions")
_SCHEMA_LISTS = ("anyOf", "allOf", "oneOf", "prefixItems")


def _is_object_schema(schema: dict[str, Any]) -> bool:
    kind = schema.get("type")
    return kind == "object" or (isinstance(kind, list) and "object" in kind) or "properties" in schema


def normalize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """A deep copy of `schema` rewritten into the structured-outputs subset (never mutates)."""
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _STRIPPED_KEYWORDS:
            continue
        if key == "minItems" and value not in (0, 1):
            continue
        if key == "format" and value not in _SUPPORTED_FORMATS:
            continue
        if key == "additionalProperties":
            continue  # always re-set below for objects
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {name: normalize_schema(sub) if isinstance(sub, dict) else sub for name, sub in value.items()}
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            out[key] = [normalize_schema(sub) if isinstance(sub, dict) else sub for sub in value]
        elif key == "items" and isinstance(value, dict):
            out[key] = normalize_schema(value)
        else:
            out[key] = value
    if "enum" in out and isinstance(out.get("type"), list):
        del out["type"]  # the enum alone pins the allowed values (incl. a literal null)
    if _is_object_schema(out):
        out["additionalProperties"] = False
    return out


strict_schema = normalize_schema  # backwards-compatible alias


_JSON_TYPES: dict[str, Any] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class _Invalid(Exception):
    """Parsed output does not conform to the caller's schema."""


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    node: Any = root
    if not ref.startswith("#/"):
        raise _Invalid(f"unsupported $ref {ref}")
    for part in ref[2:].split("/"):
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict):
        raise _Invalid(f"unresolvable $ref {ref}")
    return node


def _conform(value: Any, schema: dict[str, Any], root: dict[str, Any]) -> Any:
    """Validate `value` against the ORIGINAL schema; return it with over-long arrays truncated.

    Covers the keywords callers use (type, enum, const, required, properties, items, anyOf,
    allOf, $ref, array/number/string bounds). Raises `_Invalid` on the first violation.
    """
    if "$ref" in schema:
        return _conform(value, _resolve(schema["$ref"], root), root)
    for sub in schema.get("allOf") or []:
        value = _conform(value, sub, root)
    if "anyOf" in schema or "oneOf" in schema:
        for sub in schema.get("anyOf") or schema.get("oneOf"):
            try:
                value = _conform(value, sub, root)
                break
            except _Invalid:
                continue
        else:
            raise _Invalid("no anyOf branch matched")
    kind = schema.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(_JSON_TYPES.get(k, lambda _v: False)(value) for k in kinds):
            raise _Invalid(f"expected {kinds}")
    if "enum" in schema and value not in schema["enum"]:
        raise _Invalid("value not in enum")
    if "const" in schema and value != schema["const"]:
        raise _Invalid("value != const")
    if isinstance(value, dict):
        props: dict[str, Any] = schema.get("properties") or {}
        missing = [k for k in schema.get("required") or [] if k not in value]
        if missing:
            raise _Invalid(f"missing {missing}")
        if schema.get("additionalProperties") is False or props:
            extra = [k for k in value if k not in props]
            if extra:
                raise _Invalid(f"unexpected {extra}")
        value = {k: _conform(v, props[k], root) if k in props else v for k, v in value.items()}
    elif isinstance(value, list):
        if isinstance(schema.get("maxItems"), int):
            value = value[: schema["maxItems"]]
        if len(value) < int(schema.get("minItems") or 0):
            raise _Invalid("too few items")
        if isinstance(schema.get("items"), dict):
            value = [_conform(item, schema["items"], root) for item in value]
        if schema.get("uniqueItems") and len({repr(i) for i in value}) != len(value):
            raise _Invalid("duplicate items")
    elif isinstance(value, str):
        if len(value) < int(schema.get("minLength") or 0):
            raise _Invalid("string too short")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            raise _Invalid("string too long")
    elif _JSON_TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            raise _Invalid("below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise _Invalid("above maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise _Invalid("not above exclusiveMinimum")
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise _Invalid("not below exclusiveMaximum")
        if schema.get("multipleOf") and value % schema["multipleOf"]:
            raise _Invalid("not a multiple")
    return value


def _json_output(response: Any, schema: dict[str, Any]) -> dict[str, Any] | None:
    """The schema-conforming JSON object in the response's text, or None (absent / invalid /
    truncated / refused)."""
    if getattr(response, "stop_reason", None) in ("max_tokens", "refusal"):
        return None
    text = "".join(
        getattr(block, "text", "") or ""
        for block in getattr(response, "content", None) or []
        if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return _conform(parsed, schema, schema)
    except _Invalid:
        return None

def _usage_tokens(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    return int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)


def _map_sdk_error(exc: anthropic.APIError) -> LLMError:
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMError("timeout", "Anthropic request timed out")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMError("connection", "Anthropic connection failed")
    if isinstance(exc, anthropic.APIStatusError):
        status = exc.status_code
        request_id = getattr(exc, "request_id", None) or exc.response.headers.get("request-id")
        return LLMError(f"http_{status}", f"Anthropic HTTP {status}", status=status, request_id=request_id)
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return LLMError(f"http_{status}" if status else "connection", type(exc).__name__, status=status)


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
    """One structured-output `messages.create` (one re-ask at most).

    The request carries `output_config={"format": {"type": "json_schema", "schema":
    normalize_schema(input_schema)}}` and no tools / `tool_choice` (current models reject forced
    tool use). `tool_name` is kept for interface stability and names the output in errors and
    the re-ask; `content` is the response text parsed as JSON and checked against the ORIGINAL
    `input_schema` (see `_conform`).

    Raises `LLMUnavailable` (before any I/O) when network AI is off, `LLMError` on SDK errors
    (after the SDK's single retry) or when the re-ask still yields no valid JSON output.
    """
    if not is_available():
        raise LLMUnavailable("network AI unavailable (ANTHROPIC_API_KEY and ANTHROPIC_WORKSPACE_ID required)")
    client = get_client()
    output_config = {"format": {"type": "json_schema", "schema": normalize_schema(input_schema)}}
    prompts = (user, f"{user}\n\n{REASK_SUFFIX}")
    prompt_tokens = completion_tokens = 0
    started = time.monotonic()
    last_stop_reason: str | None = None
    for prompt in prompts:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config=output_config,
                timeout=timeout_s,
            )
        except anthropic.APIError as exc:
            raise _map_sdk_error(exc) from exc
        used_in, used_out = _usage_tokens(response)
        prompt_tokens += used_in
        completion_tokens += used_out
        last_stop_reason = getattr(response, "stop_reason", None)
        content = _json_output(response, input_schema)
        if content is not None:
            return LLMResult(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=pricing.cost_usd(model, prompt_tokens, completion_tokens),
                latency_ms=int((time.monotonic() - started) * 1000),
                model=model,
            )
    cause = "truncated" if last_stop_reason == "max_tokens" else "invalid_output"
    raise LLMError(cause, f"no valid {tool_name} JSON output after one re-ask")
