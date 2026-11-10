"""Profile drafter: CV text -> guarded ProfileInput pre-fill (spec/agent.md §Profile drafter).

Deterministic preparation -> one structured-output LLM call (`output_config` json_schema, no
tools) -> deterministic guardrails. The draft is
only a pre-fill the person reviews (Human-in-the-Loop); every failure degrades to an empty form.

`draft_profile` is pure (no DB). `run_profile_draft` is the BackgroundTask wrapper: it reads the
`cv_document` + active topics, drafts, then stores `draft_json` / `draft_status` and the one
`ai_usage` row. The CV text is untrusted: it is delimited, never logged, and nothing the model
returns is trusted without validation. Fields the spec reserves for people (verified, consent,
visibility) are never drafted.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import structlog
from sqlalchemy import select

from src.workshop0.ai import anthropic_client
from src.workshop0.ai.anthropic_client import LLMError, LLMResult, LLMUnavailable

log = structlog.get_logger("workshop0")

PURPOSE = "profile_draft"
TOOL_NAME = "submit_profile_draft"  # the schema name (a log/error label, never sent)
MAX_TOKENS = 4096
TIMEOUT_S = 25.0
CV_CALL_CHARS = 24000  # the stored extract is <=60000; only the first 24000 go to the model

MAX_TOPICS = 10
HEADLINE_MAX = 160
HEADLINE_MIN = 3
BIO_MAX = 4000
CITY_MAX = 80
URL_MAX = 300
PAST_WORK_MAX = 30
PAST_WORK_TITLE_MAX = 200
PAST_WORK_ORG_MAX = 120
YEAR_MIN = 1980

LEVELS = ("intermediate", "advanced", "expert")
DEFAULT_LEVEL = "intermediate"
PAST_WORK_KINDS = ("workshop", "talk", "course", "other")
CURRENCIES = ("INR", "USD")
RATE_UNITS = ("hour", "day", "course", "month")

# ProfileInput keys (spec/api.md §Phase 11), in contract order.
PROFILE_INPUT_KEYS = (
    "headline",
    "bio_md",
    "city",
    "remote_ok",
    "linkedin_url",
    "github_url",
    "website_url",
    "topics",
    "past_work",
    "rate_min",
    "rate_max",
    "rate_currency",
    "rate_unit",
    "pro_bono",
    "availability",
    "available_from",
    "blackouts",
)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CV_TAG = re.compile(r"<\s*/?\s*cv\s*>", re.IGNORECASE)


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


# --------------------------------------------------------------------------- prompt + schema


@lru_cache(maxsize=None)
def _prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"profile_draft_{name}.md").read_text(encoding="utf-8")


def _render(template: str, values: dict[str, str]) -> str:
    """Single-pass `{name}` substitution, so braces or placeholders inside the CV stay inert."""
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


def build_user_prompt(cv_text: str, topics: list[TopicRef]) -> str:
    """CV truncated to the call budget and fenced in `<cv>` tags it cannot close itself."""
    cv = _CV_TAG.sub("[cv-tag]", (cv_text or "")[:CV_CALL_CHARS])
    topic_lines = "\n".join(f"- {t.slug} — {t.name} — {t.category}" for t in topics) or "- (none)"
    return _render(_prompt("user"), {"topics": topic_lines, "cv": cv})


def build_input_schema(topics: list[TopicRef]) -> dict[str, Any]:
    """The structured-output JSON Schema (agent.md §Profile drafter step 2, §Schema rules).

    Every property is listed in `required`; optional values are nullable types. Length, count
    and range limits are NOT expressed here — the deterministic guardrails enforce them
    (`guard_draft`), and `anthropic_client.strict_schema` adds `additionalProperties: false`.
    """
    slug_schema: dict[str, Any] = {"type": "string"}
    if topics:
        slug_schema["enum"] = [t.slug for t in topics]
    nullable_str = {"type": ["string", "null"]}
    return {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One short line: role and focus."},
            "bio_md": {"type": "string", "description": "Short third-person summary in Markdown."},
            "city": nullable_str,
            "remote_ok": {"type": ["boolean", "null"]},
            "links": {
                "type": "object",
                "properties": {
                    "linkedin": nullable_str,
                    "github": nullable_str,
                    "website": nullable_str,
                },
                "required": ["linkedin", "github", "website"],
            },
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"slug": slug_schema, "level": {"type": "string", "enum": list(LEVELS)}},
                    "required": ["slug", "level"],
                },
            },
            "past_work": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "kind": {"type": "string", "enum": list(PAST_WORK_KINDS)},
                        "org": nullable_str,
                        "year": {"type": ["integer", "null"]},
                    },
                    "required": ["title", "kind", "org", "year"],
                },
            },
            "rate": {
                "type": "object",
                "properties": {
                    "min": {"type": ["integer", "null"]},
                    "max": {"type": ["integer", "null"]},
                    "currency": {"type": ["string", "null"], "enum": [*CURRENCIES, None]},
                    "unit": {"type": ["string", "null"], "enum": [*RATE_UNITS, None]},
                    "pro_bono": {"type": ["boolean", "null"]},
                },
                "required": ["min", "max", "currency", "unit", "pro_bono"],
            },
            "availability_notes": nullable_str,
        },
        "required": [
            "headline",
            "bio_md",
            "city",
            "remote_ok",
            "links",
            "topics",
            "past_work",
            "rate",
            "availability_notes",
        ],
    }


# --------------------------------------------------------------------------- guardrails


def _clean_text(value: Any, limit: int, *, multiline: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", value)
    text = _CONTROL_CHARS.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        text = " ".join(text.split())
    return text.strip()[:limit].strip()


def _squash(text: str) -> str:
    """Lower-case, whitespace-free form used for evidence checks against the CV."""
    return re.sub(r"\s+", "", text).lower()


def _link_core(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    return _squash(f"{host}{parts.path}").rstrip("/")


def sanitize_url(value: Any, *, host: str | None, cv_squashed: str) -> str | None:
    """Keep only an `https://` URL (scheme-less input is read as https) on the right host
    (`host` or a subdomain of it; any host when None) that is actually printed in the CV."""
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw or len(raw) > URL_MAX or any(ch.isspace() for ch in raw):
        return None
    if "://" not in raw:
        raw = f"https://{raw.lstrip('/')}"
    try:
        parts = urlsplit(raw)
        port = parts.port  # raises on a malformed port
    except ValueError:
        return None
    hostname = (parts.hostname or "").lower()
    if parts.scheme.lower() != "https" or not hostname or "." not in hostname:
        return None
    if parts.username or parts.password or port not in (None, 443):
        return None
    if host is not None and hostname != host and not hostname.endswith(f".{host}"):
        return None
    core = _link_core(raw)
    if not core or core not in cv_squashed:
        return None  # never invent links: it must appear in the CV
    url = urlunsplit(("https", hostname, parts.path, parts.query, ""))
    return url if len(url) <= URL_MAX else None


def _guard_topics(raw: Any, allowed: dict[str, TopicRef]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("slug"), str):
            continue
        slug = item["slug"].strip().lower()
        if slug not in allowed or slug in seen:
            continue
        level = item.get("level")
        level = level.strip().lower() if isinstance(level, str) else ""
        out.append({"slug": slug, "level": level if level in LEVELS else DEFAULT_LEVEL})
        seen.add(slug)
        if len(out) == MAX_TOPICS:
            break
    return out


def _guard_year(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, int) and YEAR_MIN <= value <= datetime.now(timezone.utc).year:
        return value
    return None


def _guard_past_work(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"), PAST_WORK_TITLE_MAX)
        if not title:
            continue
        kind = item.get("kind")
        kind = kind.strip().lower() if isinstance(kind, str) else ""
        org = _clean_text(item.get("org"), PAST_WORK_ORG_MAX) or None
        out.append(
            {
                "title": title,
                "kind": kind if kind in PAST_WORK_KINDS else "other",
                "org": org,
                "year": _guard_year(item.get("year")),
            }
        )
        if len(out) == PAST_WORK_MAX:
            break
    return out


_AMOUNT = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(k|lakhs?|lacs?|l)?(?![a-z\d])", re.IGNORECASE)
_DIGIT_GROUPING = re.compile(r"(?<=\d),(?=\d)")
_MULTIPLIERS = {"k": 1000, "l": 100_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000}


def cv_amounts(cv_text: str) -> set[int]:
    """Every whole amount printed in the CV, as standalone numbers: `45000`, `45,000`,
    `1,20,000`, `45k`, `1.5 lakh`. Digits inside other numbers never count (`5` is not in
    `45000`)."""
    text = _DIGIT_GROUPING.sub("", cv_text or "")
    amounts: set[int] = set()
    for number, suffix in _AMOUNT.findall(text):
        value = float(number) * _MULTIPLIERS.get(suffix.lower(), 1) if suffix else float(number)
        if value.is_integer():
            amounts.add(int(value))
    return amounts


def _guard_rate(raw: Any, cv_amounts_: set[int]) -> dict[str, Any]:
    empty = {"rate_min": None, "rate_max": None, "rate_currency": None, "rate_unit": None}
    pro_bono = None
    if not isinstance(raw, dict):
        return {**empty, "pro_bono": None}
    if isinstance(raw.get("pro_bono"), bool):
        pro_bono = raw["pro_bono"]

    def _int(v: Any) -> int | None:
        return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None

    low, high = _int(raw.get("min")), _int(raw.get("max"))
    if (raw.get("min") is not None and low is None) or (raw.get("max") is not None and high is None):
        return {**empty, "pro_bono": pro_bono}  # a non-integer / non-positive amount: drop the rate
    if low is None and high is None:
        return {**empty, "pro_bono": pro_bono}
    if low is not None and high is not None and low > high:
        return {**empty, "pro_bono": pro_bono}
    currency = raw.get("currency").strip().upper() if isinstance(raw.get("currency"), str) else None
    unit = raw.get("unit").strip().lower() if isinstance(raw.get("unit"), str) else None
    if currency not in CURRENCIES or unit not in RATE_UNITS:
        return {**empty, "pro_bono": pro_bono}
    if not all(v in cv_amounts_ for v in (low, high) if v is not None):
        return {**empty, "pro_bono": pro_bono}  # never invent rates
    return {
        "rate_min": low,
        "rate_max": high,
        "rate_currency": currency,
        "rate_unit": unit,
        "pro_bono": pro_bono,
    }


def _is_filled(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def autofilled_fields_of(draft: dict[str, Any]) -> list[str]:
    """The ProfileInput keys whose guarded value is non-empty (drives "From your CV")."""
    return [key for key in PROFILE_INPUT_KEYS if _is_filled(draft.get(key))]


def guard_draft(content: Any, cv_text: str, topics: list[TopicRef]) -> dict[str, Any] | None:
    """Apply every deterministic guardrail; returns the ProfileInput-shaped draft, or None when
    no valid headline can be produced (the draft fails)."""
    content = content if isinstance(content, dict) else {}
    allowed = {t.slug: t for t in topics}
    cv_squashed = _squash(cv_text or "")
    amounts = cv_amounts(cv_text)

    guarded_topics = _guard_topics(content.get("topics"), allowed)
    past_work = _guard_past_work(content.get("past_work"))
    links = content.get("links") if isinstance(content.get("links"), dict) else {}

    headline = _clean_text(content.get("headline"), HEADLINE_MAX)
    if len(headline) < HEADLINE_MIN:
        if past_work and guarded_topics:
            fallback = f"{past_work[0]['title']} · {allowed[guarded_topics[0]['slug']].name}"
            headline = _clean_text(fallback, HEADLINE_MAX)
        else:
            headline = ""
    if len(headline) < HEADLINE_MIN:
        return None

    remote_ok = content.get("remote_ok")
    draft: dict[str, Any] = {
        "headline": headline,
        "bio_md": _clean_text(content.get("bio_md"), BIO_MAX, multiline=True),
        "city": _clean_text(content.get("city"), CITY_MAX) or None,
        "remote_ok": remote_ok if isinstance(remote_ok, bool) else None,
        "linkedin_url": sanitize_url(links.get("linkedin"), host="linkedin.com", cv_squashed=cv_squashed),
        "github_url": sanitize_url(links.get("github"), host="github.com", cv_squashed=cv_squashed),
        "website_url": sanitize_url(links.get("website"), host=None, cv_squashed=cv_squashed),
        "topics": guarded_topics,
        "past_work": past_work,
        **_guard_rate(content.get("rate"), amounts),
        # Never drafted from a CV: the weekly pattern, dates and blackouts are the person's call.
        "availability": {},
        "available_from": None,
        "blackouts": [],
    }
    return {key: draft[key] for key in PROFILE_INPUT_KEYS}


# --------------------------------------------------------------------------- entry points


def draft_profile(cv_text: str, topics: list[TopicRef]) -> DraftResult:
    """Pure: one LLM call + guardrails, no DB. Raises LLMUnavailable / LLMError / DraftRejected."""
    from src.workshop0.config.settings import get_settings

    result = anthropic_client.call_json(
        system=_prompt("system"),
        user=build_user_prompt(cv_text, topics),
        tool_name=TOOL_NAME,
        input_schema=build_input_schema(topics),
        model=get_settings().workshop0_ai_network_model,
        max_tokens=MAX_TOKENS,
        timeout_s=TIMEOUT_S,
    )
    draft = guard_draft(result.content, cv_text, topics)
    if draft is None:
        raise DraftRejected(result, "no usable headline in the model output")
    return DraftResult(draft=draft, autofilled_fields=autofilled_fields_of(draft), llm=result)


def _cv_version(cv: Any) -> tuple[str | None, Any]:
    """Identity of the CV content a draft is made from. Replacing a CV keeps the row id but
    rewrites `sha256` and `created_at`, so a stale draft can be told apart from a fresh one."""
    return (cv.sha256, cv.created_at)


def _load_inputs(cv_document_id: int) -> tuple[str, list[TopicRef], tuple[str | None, Any]] | None:
    from src.workshop0.db.models import CvDocument, Topic
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        cv = session.get(CvDocument, cv_document_id)
        if cv is None:
            return None
        rows = session.scalars(
            select(Topic).where(Topic.active.is_(True)).order_by(Topic.position, Topic.id)
        ).all()
        return (
            cv.text_extract or "",
            [TopicRef(t.slug, t.name, t.category) for t in rows],
            _cv_version(cv),
        )


def _store(
    cv_document_id: int,
    *,
    status: str,
    draft: dict[str, Any] | None = None,
    llm: LLMResult | None = None,
    version: tuple[str | None, Any] | None = None,
) -> None:
    from src.workshop0.ai.usage import record_usage
    from src.workshop0.db.models import CvDocument
    from src.workshop0.db.session import create_db_session

    with create_db_session() as session:
        cv = session.get(CvDocument, cv_document_id, with_for_update=True)
        if cv is not None and version is not None and _cv_version(cv) != version:
            # The CV was replaced while this draft was in flight: the newer CV's own task
            # owns draft_status/draft_json. Checked under the row lock, so no lost update.
            log.info("ai.profile_draft_stale", cv_document_id=cv_document_id)
        elif cv is not None:
            cv.draft_status = status
            cv.draft_json = json.dumps(draft, ensure_ascii=False) if draft is not None else None
        if llm is not None:
            # The spend is real even if the CV row was replaced/deleted meanwhile.
            record_usage(
                session,
                llm,
                purpose=PURPOSE,
                cv_document_id=cv_document_id if cv is not None else None,
            )


def _log_failure(cv_document_id: int, cause: str, exc: BaseException) -> None:
    status = cause.removeprefix("http_") if cause.startswith("http_") else None
    log.error(
        "ai.call_failed",
        purpose=PURPOSE,
        cv_document_id=cv_document_id,
        cause=cause,
        status=getattr(exc, "status", None) or status,
        request_id=getattr(exc, "request_id", None),
    )


def run_profile_draft(cv_document_id: int) -> None:
    """BackgroundTask wrapper: loads the CV document, drafts, stores the result and usage.

    `draft_status`: pending -> `ready` | `skipped` (network AI unavailable) | `failed`. Never
    raises (a background task has no caller to report to); no DB connection is held across the
    LLM call.
    """
    version = None
    try:
        inputs = _load_inputs(cv_document_id)
        if inputs is None:
            log.warning("ai.profile_draft_missing_cv", cv_document_id=cv_document_id)
            return
        cv_text, topics, version = inputs
        try:
            result = draft_profile(cv_text, topics)
        except LLMUnavailable:
            _store(cv_document_id, status="skipped", version=version)
            log.info("ai.profile_draft_skipped", cv_document_id=cv_document_id, reason="unavailable")
            return
        except LLMError as exc:
            _log_failure(cv_document_id, exc.cause, exc)
            _store(cv_document_id, status="failed", version=version)
            return
        except DraftRejected as exc:
            _log_failure(cv_document_id, "guardrail_rejected", exc)
            _store(cv_document_id, status="failed", llm=exc.llm, version=version)
            return
        _store(cv_document_id, status="ready", draft=result.draft, llm=result.llm, version=version)
    except Exception as exc:  # noqa: BLE001 — never leave a CV stuck in `pending`
        _log_failure(cv_document_id, "internal_error", exc)
        try:
            _store(cv_document_id, status="failed", version=version)
        except Exception:  # noqa: BLE001
            log.exception("ai.profile_draft_store_failed", cv_document_id=cv_document_id)
