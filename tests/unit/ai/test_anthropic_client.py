"""Network-AI client contract, no network (spec/agent.md §Testing — workspace header).

Every request goes through an in-process `httpx2.MockTransport` (the anthropic>=2 SDK ships
its own httpx fork and rejects plain `httpx` clients). Credentials here are FAKE values set
on the live settings instance, so a failing assertion can never print the real `.env` key.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx2
import pytest

from src.workshop0.ai import anthropic_client
from src.workshop0.ai.anthropic_client import LLMError, LLMResult, LLMUnavailable
from src.workshop0.config.settings import Settings, get_settings

FAKE_KEY = "sk-ant-unit-fake-key-0001"
FAKE_WORKSPACE = "wrkspc_unit_fake_0001"
TOOL = "submit_pair"
SCHEMA = {
    "type": "object",
    "properties": {"word": {"type": "string"}, "number": {"type": "integer"}},
    "required": ["word", "number"],
}
MODEL = "claude-haiku-5-5"


def _message(content: list[dict], *, stop_reason: str = "end_turn", tokens: tuple[int, int] = (11, 7)) -> dict:
    return {
        "id": "msg_unit",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
    }


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _json_reply(payload: object, **kwargs) -> dict:
    """What structured outputs return: one text block holding the JSON document."""
    return _message([_text(json.dumps(payload))], **kwargs)


def _tool_use(payload: dict, name: str = TOOL) -> dict:
    return {"type": "tool_use", "id": "toolu_unit", "name": name, "input": payload}


TEXT_ONLY = _message([_text("Sure, here you go: word=hi")])
GOOD = _json_reply({"word": "hello", "number": 3})


class Recorder:
    """A MockTransport handler that replays canned (status, body) replies in order."""

    def __init__(self, *replies: tuple[int, dict]) -> None:
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        status, body = self.replies[min(len(self.requests), len(self.replies)) - 1]
        return httpx2.Response(status, json=body, headers={"request-id": f"req_unit_{len(self.requests)}"})

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


@pytest.fixture
def fake_credentials(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", FAKE_KEY)
    monkeypatch.setattr(settings, "anthropic_workspace_id", FAKE_WORKSPACE)
    anthropic_client.reset_client()
    yield settings
    anthropic_client.reset_client()


@pytest.fixture
def mock_client(monkeypatch, fake_credentials):
    """Factory: route `call_json` through a MockTransport client built by `build_client`."""

    def _install(recorder: Recorder):
        def _get_client():
            return anthropic_client.build_client(
                get_settings(), http_client=httpx2.Client(transport=httpx2.MockTransport(recorder))
            )

        monkeypatch.setattr(anthropic_client, "get_client", _get_client)
        return recorder

    return _install


def _call(**overrides) -> LLMResult:
    kwargs = {
        "system": "You extract a word and a number.",
        "user": "The word is hello and the number is 3.",
        "tool_name": TOOL,
        "input_schema": SCHEMA,
        "model": MODEL,
        "max_tokens": 64,
        "timeout_s": 5,
    }
    kwargs.update(overrides)
    return anthropic_client.call_json(**kwargs)


def _assert_carries_credentials(request: httpx2.Request) -> None:
    assert request.headers.get("anthropic-workspace-id") == FAKE_WORKSPACE
    # anthropic>=2 sends the key as `Authorization: Bearer <key>` (older SDKs: `x-api-key`).
    sent = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")
    assert sent == FAKE_KEY


# ------------------------------------------------------------------ happy path + header


def test_call_json_returns_parsed_json_and_sends_workspace_header(mock_client):
    recorder = mock_client(Recorder((200, GOOD)))

    result = _call()

    assert result.content == {"word": "hello", "number": 3}
    assert (result.prompt_tokens, result.completion_tokens) == (11, 7)
    assert result.model == MODEL
    assert result.cost_usd == Decimal("0.000046")  # 11 * 1.00/M + 7 * 5.00/M
    assert result.latency_ms >= 0
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.url.path == "/v1/messages"
    _assert_carries_credentials(request)
    body = recorder.bodies()[0]
    assert body["model"] == MODEL
    assert body["max_tokens"] == 64
    assert body["output_config"] == {
        "format": {"type": "json_schema", "schema": {**SCHEMA, "additionalProperties": False}}
    }
    # structured outputs, never a forced tool call (claude-sonnet-5-5 rejects tool_choice tool/any)
    assert "tool_choice" not in body
    assert "tools" not in body
    assert body["system"] == "You extract a word and a number."
    assert body["messages"] == [{"role": "user", "content": "The word is hello and the number is 3."}]


def test_call_json_does_not_mutate_the_callers_schema(mock_client):
    mock_client(Recorder((200, GOOD)))
    schema = {
        "type": "object",
        "properties": {"word": {"type": "string"}, "number": {"type": "integer", "minimum": 0}},
        "required": ["word", "number"],
    }
    snapshot = json.loads(json.dumps(schema))

    _call(input_schema=schema)

    assert schema == snapshot


def test_build_client_sets_workspace_default_header_and_single_retry(fake_credentials):
    client = anthropic_client.build_client(fake_credentials)
    assert client.default_headers.get("anthropic-workspace-id") == FAKE_WORKSPACE
    assert client.max_retries == 1


# ------------------------------------------------------------------ re-ask path


def test_reask_on_non_json_output_carries_header_on_both_requests(mock_client):
    recorder = mock_client(Recorder((200, TEXT_ONLY), (200, _json_reply({"word": "hi", "number": 1}, tokens=(20, 9)))))

    result = _call()

    assert result.content == {"word": "hi", "number": 1}
    assert len(recorder.requests) == 2
    for request in recorder.requests:
        _assert_carries_credentials(request)
    first, second = recorder.bodies()
    assert second["messages"][0]["content"].endswith(anthropic_client.REASK_SUFFIX)
    assert second["messages"][0]["content"].startswith(first["messages"][0]["content"])
    assert second["output_config"] == first["output_config"]
    assert "tool_choice" not in first and "tool_choice" not in second
    # tokens are summed over the re-ask, and cost follows the summed tokens
    assert (result.prompt_tokens, result.completion_tokens) == (11 + 20, 7 + 9)
    assert result.cost_usd == Decimal("0.000111")


def test_reask_twice_without_valid_output_raises_invalid_output(mock_client):
    recorder = mock_client(Recorder((200, TEXT_ONLY), (200, TEXT_ONLY)))

    with pytest.raises(LLMError) as excinfo:
        _call()

    assert excinfo.value.cause == "invalid_output"
    assert len(recorder.requests) == 2  # exactly one re-ask, never a third request
    for request in recorder.requests:
        _assert_carries_credentials(request)


def test_max_tokens_stop_triggers_reask_then_truncated(mock_client):
    truncated = _message([_text('{"word": "hel')], stop_reason="max_tokens")
    recorder = mock_client(Recorder((200, truncated), (200, truncated)))

    with pytest.raises(LLMError) as excinfo:
        _call()

    assert excinfo.value.cause == "truncated"
    assert len(recorder.requests) == 2


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(_json_reply({"word": "hello"}), id="missing-required"),
        pytest.param(_json_reply({"word": "hello", "number": "3"}), id="wrong-type"),
        pytest.param(_json_reply({"word": "hello", "number": True}), id="bool-is-not-integer"),
        pytest.param(_json_reply({"word": "hi", "number": 3, "extra": 1}), id="extra-key"),
        pytest.param(_json_reply(["hello", 3]), id="top-level-array"),
        pytest.param(_message([]), id="empty-content"),
        pytest.param(_message([_text("   ")]), id="blank-text"),
        pytest.param(_message([_tool_use({"word": "x", "number": 1})]), id="tool-use-block-ignored"),
        pytest.param(_message([_text('{"word": "x", "number": 1}')], stop_reason="refusal"), id="refusal"),
    ],
)
def test_schema_invalid_output_triggers_one_reask(mock_client, bad):
    recorder = mock_client(Recorder((200, bad), (200, GOOD)))

    assert _call().content == {"word": "hello", "number": 3}
    assert len(recorder.requests) == 2


def test_stripped_constraints_are_enforced_in_python(mock_client):
    """Bounds the strict-mode API rejects are removed from the request but still hold."""
    schema = {
        "type": "object",
        "properties": {
            "number": {"type": "integer", "minimum": 1, "maximum": 5},
            "tags": {"type": "array", "maxItems": 2, "items": {"type": "string"}},
        },
        "required": ["number", "tags"],
    }
    recorder = mock_client(
        Recorder(
            (200, _json_reply({"number": 9, "tags": []})),  # out of range -> re-ask
            (200, _json_reply({"number": 4, "tags": ["a", "b", "c"]})),  # over maxItems -> truncated
        )
    )

    result = _call(input_schema=schema)

    assert result.content == {"number": 4, "tags": ["a", "b"]}
    sent = recorder.bodies()[0]["output_config"]["format"]["schema"]
    assert sent["properties"]["number"] == {"type": "integer"}
    assert sent["properties"]["tags"] == {"type": "array", "items": {"type": "string"}}


# ------------------------------------------------------------------ strict-schema normaliser


def test_normalize_schema_closes_every_object_recursively():
    schema = {
        "type": "object",
        "properties": {
            "links": {"type": "object", "properties": {"a": {"type": ["string", "null"]}}, "required": ["a"]},
            "rows": {
                "type": "array",
                "items": {"type": "object", "properties": {"x": {"$ref": "#/$defs/X"}}, "required": ["x"]},
            },
            "maybe": {"anyOf": [{"type": "object", "properties": {"q": {"type": "string"}}}, {"type": "null"}]},
        },
        "required": ["links", "rows", "maybe"],
        "$defs": {"X": {"type": "object", "properties": {"y": {"type": "integer"}}, "additionalProperties": True}},
    }

    out = anthropic_client.normalize_schema(schema)

    assert out["additionalProperties"] is False
    assert out["properties"]["links"]["additionalProperties"] is False
    assert out["properties"]["rows"]["items"]["additionalProperties"] is False
    assert out["properties"]["maybe"]["anyOf"][0]["additionalProperties"] is False
    assert "additionalProperties" not in out["properties"]["maybe"]["anyOf"][1]
    assert out["$defs"]["X"]["additionalProperties"] is False  # a permissive value is overridden
    assert "additionalProperties" not in out["properties"]["links"]["properties"]["a"]  # not an object
    assert "additionalProperties" not in schema  # input untouched


def test_normalize_schema_strips_unsupported_keywords_and_keeps_supported_ones():
    schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 0, "maximum": 9, "multipleOf": 3, "description": "d"},
            "f": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
            "a": {"type": "array", "maxItems": 3, "minItems": 2, "uniqueItems": True, "items": {"type": "string"}},
            "a1": {"type": "array", "minItems": 1, "items": {"type": "string"}},
            "s": {"type": "string", "minLength": 1, "maxLength": 9, "pattern": "^x", "format": "uri"},
            "s2": {"type": "string", "format": "made-up"},
        },
        "required": ["n"],
    }

    props = anthropic_client.normalize_schema(schema)["properties"]

    assert props["n"] == {"type": "integer", "description": "d"}
    assert props["f"] == {"type": "number"}
    assert props["a"] == {"type": "array", "items": {"type": "string"}}
    assert props["a1"] == {"type": "array", "minItems": 1, "items": {"type": "string"}}
    assert props["s"] == {"type": "string", "minLength": 1, "maxLength": 9, "pattern": "^x", "format": "uri"}
    assert props["s2"] == {"type": "string"}


def test_normalize_schema_drops_list_type_next_to_enum():
    """The API rejects `{"type": ["string","null"], "enum": [...]}`; the enum alone suffices."""
    nullable_enum = {"type": ["string", "null"], "enum": ["EUR", "USD", None], "description": "c"}
    plain_enum = {"type": "string", "enum": ["a", "b"]}

    out = anthropic_client.normalize_schema(
        {"type": "object", "properties": {"c": nullable_enum, "p": plain_enum}, "required": ["c", "p"]}
    )

    assert out["properties"]["c"] == {"enum": ["EUR", "USD", None], "description": "c"}
    assert out["properties"]["p"] == plain_enum


def test_nullable_enum_output_still_validates_against_the_original_schema(mock_client):
    schema = {
        "type": "object",
        "properties": {"c": {"type": ["string", "null"], "enum": ["EUR", None]}},
        "required": ["c"],
    }
    mock_client(Recorder((200, _json_reply({"c": "GBP"})), (200, _json_reply({"c": None}))))

    assert _call(input_schema=schema).content == {"c": None}


# ------------------------------------------------------------------ error mapping


@pytest.mark.parametrize("status", [400, 401, 404])
def test_4xx_maps_to_http_status_without_retry(mock_client, status):
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": "bad"}}
    recorder = mock_client(Recorder((status, error)))

    with pytest.raises(LLMError) as excinfo:
        _call()

    assert excinfo.value.cause == f"http_{status}"
    assert excinfo.value.status == status
    assert excinfo.value.request_id == "req_unit_1"
    assert len(recorder.requests) == 1  # 400/401/404 are not retried by the SDK
    _assert_carries_credentials(recorder.requests[0])


@pytest.mark.parametrize("status", [429, 500, 529])
def test_retryable_status_is_retried_once_then_mapped(mock_client, status, monkeypatch):
    monkeypatch.setattr("anthropic._base_client.time.sleep", lambda _s: None, raising=False)
    error = {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}}
    recorder = mock_client(Recorder((status, error)))

    with pytest.raises(LLMError) as excinfo:
        _call()

    assert excinfo.value.cause == f"http_{status}"
    assert len(recorder.requests) == 2  # SDK max_retries=1
    for request in recorder.requests:
        _assert_carries_credentials(request)


def test_retryable_status_then_success_returns_result(mock_client, monkeypatch):
    monkeypatch.setattr("anthropic._base_client.time.sleep", lambda _s: None, raising=False)
    error = {"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}
    recorder = mock_client(Recorder((529, error), (200, GOOD)))

    assert _call().content == {"word": "hello", "number": 3}
    assert len(recorder.requests) == 2


def test_timeout_maps_to_timeout_cause(mock_client, monkeypatch):
    monkeypatch.setattr("anthropic._base_client.time.sleep", lambda _s: None, raising=False)

    class TimingOut(Recorder):
        def __call__(self, request):
            self.requests.append(request)
            raise httpx2.ReadTimeout("timed out", request=request)

    recorder = mock_client(TimingOut())

    with pytest.raises(LLMError) as excinfo:
        _call()

    assert excinfo.value.cause == "timeout"
    assert len(recorder.requests) == 2  # one SDK retry


def test_connection_error_maps_to_llm_error(mock_client, monkeypatch):
    monkeypatch.setattr("anthropic._base_client.time.sleep", lambda _s: None, raising=False)

    class Refusing(Recorder):
        def __call__(self, request):
            self.requests.append(request)
            raise httpx2.ConnectError("refused", request=request)

    mock_client(Refusing())

    with pytest.raises(LLMError) as excinfo:
        _call()

    assert excinfo.value.cause == "connection"


def test_llm_error_message_never_contains_credentials(mock_client):
    error = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    mock_client(Recorder((401, error)))

    with pytest.raises(LLMError) as excinfo:
        _call()

    rendered = f"{excinfo.value!s} {excinfo.value!r} {excinfo.value.cause}"
    assert FAKE_KEY not in rendered and FAKE_WORKSPACE not in rendered


# ------------------------------------------------------------------ availability rule


@pytest.mark.parametrize("which", ["workspace", "key"])
def test_missing_key_or_workspace_sends_zero_requests(mock_client, network_ai_disabled, which):
    recorder = mock_client(Recorder((200, GOOD)))
    network_ai_disabled(which=which)

    assert anthropic_client.is_available() is False
    with pytest.raises(LLMUnavailable):
        _call()
    assert recorder.requests == []


def test_whitespace_only_workspace_counts_as_missing(mock_client, monkeypatch):
    recorder = mock_client(Recorder((200, GOOD)))
    monkeypatch.setattr(get_settings(), "anthropic_workspace_id", "   ")

    assert anthropic_client.is_available() is False
    with pytest.raises(LLMUnavailable):
        _call()
    assert recorder.requests == []


def test_both_values_set_is_available(fake_credentials):
    assert anthropic_client.is_available() is True


# ------------------------------------------------------------------ client cache


def test_get_client_is_cached_and_reset_drops_it(fake_credentials):
    first = anthropic_client.get_client()
    assert anthropic_client.get_client() is first
    anthropic_client.reset_client()
    assert anthropic_client.get_client() is not first


def test_get_client_rebuilds_when_credentials_change(fake_credentials, monkeypatch):
    first = anthropic_client.get_client()
    monkeypatch.setattr(fake_credentials, "anthropic_workspace_id", "wrkspc_unit_other")
    second = anthropic_client.get_client()
    assert second is not first
    assert second.default_headers.get("anthropic-workspace-id") == "wrkspc_unit_other"


# ------------------------------------------------------------------ settings defaults


def test_network_model_defaults():
    defaults = Settings.model_fields
    assert defaults["workshop0_ai_network_model"].default == "claude-sonnet-5-5"
    assert defaults["workshop0_ai_network_fast_model"].default == "claude-haiku-5-5"
    assert defaults["anthropic_api_key"].default == ""
    assert defaults["anthropic_workspace_id"].default == ""
