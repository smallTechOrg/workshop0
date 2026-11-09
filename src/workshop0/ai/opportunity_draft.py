"""Opportunity drafter: a forwarded partner post -> guarded editor pre-fill
(spec/agent.md §Opportunity drafter).

Deterministic preparation -> one structured-output call (`call_json`, no tools) -> deterministic
guardrails. The draft is only a pre-fill the admin reviews (Human-in-the-Loop): this module never
creates, saves or publishes a listing, and writes nothing but the one `ai_usage` row.

`draft_opportunity` is pure (no DB). `run_opportunity_draft` is the endpoint helper: it loads the
active topics + partners, drafts, records usage and maps failures to API errors. The pasted post
is untrusted: it is delimited, never logged, and nothing the model returns is trusted without
validation (exact enums, curated topics, scrubbed identity and contacts).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.ai import anthropic_client
from src.workshop0.ai.anthropic_client import LLMError, LLMResult, LLMUnavailable
from src.workshop0.ai.profile_draft import TopicRef
from src.workshop0.api._common import api_error
from src.workshop0.services.locations import CITY_MAX, COUNTRY_MAX, LOCATIONS_MAX, collapse, location_key

log = structlog.get_logger("workshop0")

PURPOSE = "opportunity_draft"
TOOL_NAME = "submit_opportunity_draft"  # the schema name (a log/error label, never sent)
MAX_TOKENS = 4096
TIMEOUT_S = 20.0
POST_CALL_CHARS = 20000
PARTNER_CAP = 300

TITLE_MAX, TITLE_MIN = 160, 3
SUMMARY_MAX = 280
DESCRIPTION_MAX = 20000
DURATION_MAX = 80
NOTE_MAX = 120
INTERNAL_NOTES_MAX = 5000
PARTNER_NAME_MAX = 160
MAX_TOPICS = 8
AMOUNT_MAX = 100_000_000
GENERIC_PARTNER = "a smallTech partner"

TYPES = ("workshop", "engagement", "role", "cofacilitation")
LOCATION_MODES = ("remote", "onsite", "hybrid")
CURRENCIES = ("INR", "USD")
UNITS = ("hour", "day", "course", "month")

# api.md §Phase 11b `drafted_fields` values, in contract order.
DRAFTED_FIELD_KEYS = (
    "title",
    "type",
    "summary",
    "description_md",
    "topics",
    "location",
    "dates",
    "duration_text",
    "deadline",
    "compensation",
    "partner",
    "partner_display_name",
    "internal_notes",
)

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_POST_TAG = re.compile(r"<\s*/?\s*forwarded_post\s*>", re.IGNORECASE)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_LEGAL_SUFFIX = re.compile(
    r"[\s,.]*\b(?:pvt\.?\s*ltd|private\s+limited|ltd|llp|inc|llc|gmbh)\b\.?\s*$", re.IGNORECASE
)


@dataclass(frozen=True)
class PartnerRef:
    id: int
    internal_name: str
    display_name: str | None


@dataclass(frozen=True)
class OpportunityDraftResult:
    draft: dict[str, Any]
    drafted_fields: list[str]
    llm: LLMResult


class OpportunityDraftRejected(Exception):
    """The guardrails left nothing usable; carries the spent call for usage recording."""

    def __init__(self, llm: LLMResult, message: str = "draft rejected by guardrails") -> None:
        super().__init__(message)
        self.llm = llm


# --------------------------------------------------------------------------- prompt + schema


@lru_cache(maxsize=None)
def _prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"opportunity_draft_{name}.md").read_text(encoding="utf-8")


def _render(template: str, values: dict[str, str]) -> str:
    """Single-pass `{name}` substitution, so braces or placeholders inside the post stay inert."""
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), template)


def prepare_text(text: str) -> str:
    return (text or "").strip()[:POST_CALL_CHARS]


def build_user_prompt(
    text: str,
    *,
    topics: list[TopicRef],
    partners: list[PartnerRef],
    keep_partner_identity: bool,
    today: date,
) -> str:
    """Post trimmed/truncated and fenced in `<forwarded_post>` tags it cannot close itself."""
    post = _POST_TAG.sub("[post-tag]", prepare_text(text))
    topic_lines = "\n".join(f"- {t.slug} — {t.name} ({t.category})" for t in topics) or "- (none)"
    partner_lines = "\n".join(f"- {p.id} — {p.internal_name}" for p in partners) or "- (none)"
    return _render(
        _prompt("user"),
        {
            "today": today.isoformat(),
            "keep_partner_identity": "true" if keep_partner_identity else "false",
            "topics": topic_lines,
            "partners": partner_lines,
            "post": post,
        },
    )


def build_input_schema(topics: list[TopicRef]) -> dict[str, Any]:
    """The structured-output JSON Schema (agent.md §Opportunity drafter step 2, §Schema rules).

    Every property is required; optional values are nullable types; enums allow null. No length
    or count limits — the guardrails enforce them (`normalize_schema` adds
    `additionalProperties: false`)."""
    nullable_str: dict[str, Any] = {"type": ["string", "null"]}
    nullable_int: dict[str, Any] = {"type": ["integer", "null"]}
    slug_schema: dict[str, Any] = {"type": "string"}
    if topics:
        slug_schema["enum"] = [t.slug for t in topics]

    def nullable_enum(values: tuple[str, ...]) -> dict[str, Any]:
        return {"type": ["string", "null"], "enum": [*values, None]}

    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "type": nullable_enum(TYPES),
            "summary": {"type": "string"},
            "description_md": {"type": "string"},
            "topics": {"type": "array", "items": slug_schema},
            "location_mode": nullable_enum(LOCATION_MODES),
            "locations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}, "country": nullable_str},
                    "required": ["city", "country"],
                },
            },
            "starts_on": nullable_str,
            "ends_on": nullable_str,
            "duration_text": nullable_str,
            "deadline_on": nullable_str,
            "compensation": {
                "type": "object",
                "properties": {
                    "min": nullable_int,
                    "max": nullable_int,
                    "currency": nullable_enum(CURRENCIES),
                    "unit": nullable_enum(UNITS),
                    "note": nullable_str,
                },
                "required": ["min", "max", "currency", "unit", "note"],
            },
            "partner": {
                "type": "object",
                "properties": {
                    "existing_partner_id": nullable_int,
                    "organisation_name": nullable_str,
                    "suggested_display_name": nullable_str,
                },
                "required": ["existing_partner_id", "organisation_name", "suggested_display_name"],
            },
            "internal_notes": nullable_str,
        },
        "required": [
            "title",
            "type",
            "summary",
            "description_md",
            "topics",
            "location_mode",
            "locations",
            "starts_on",
            "ends_on",
            "duration_text",
            "deadline_on",
            "compensation",
            "partner",
            "internal_notes",
        ],
    }


# --------------------------------------------------------------------------- guardrails


def _clean(value: Any, limit: int, *, multiline: bool = False) -> str:
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFC", value)
    text = _CONTROL_CHARS.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        text = " ".join(text.split())
    return text.strip()[:limit].strip()


def _enum(value: Any, allowed: tuple[str, ...]) -> str | None:
    """Exact enum member or null — no trimming, case-folding or fuzzy matching."""
    return value if isinstance(value, str) and value in allowed else None


def _guard_topics(raw: Any, allowed: set[str]) -> list[str]:
    out: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, str):
            continue
        slug = item.strip().lower()
        if slug in allowed and slug not in out:
            out.append(slug)
            if len(out) == MAX_TOPICS:
                break
    return out


def _guard_date(value: Any, today: date) -> date | None:
    if not isinstance(value, str) or not _ISO_DATE.match(value.strip()):
        return None
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return None
    if not (today.year - 1 <= parsed.year <= today.year + 3):
        return None
    return parsed


def _amount(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= AMOUNT_MAX else None


def _guard_compensation(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    low, high = _amount(raw.get("min")), _amount(raw.get("max"))
    if low is not None and high is not None and low > high:
        low = high = None
    currency, unit = _enum(raw.get("currency"), CURRENCIES), _enum(raw.get("unit"), UNITS)
    if low is None and high is None:
        currency = unit = None
    return {
        "compensation_min": low,
        "compensation_max": high,
        "compensation_currency": currency,
        "compensation_unit": unit,
        "compensation_text": _clean(raw.get("note"), NOTE_MAX) or None,
    }


def _name_variants(name: str) -> list[str]:
    """`name` and (when it ends in a legal suffix) the name without it."""
    collapsed = " ".join(name.split())
    stripped = _LEGAL_SUFFIX.sub("", collapsed).strip(" ,.")
    return [v for v in (collapsed, stripped) if v]


def _scrub_pattern(names: set[str]) -> re.Pattern[str] | None:
    """Case-insensitive whole-word alternation, longest first, whitespace-flexible."""
    parts = [
        r"\s+".join(re.escape(word) for word in name.split())
        for name in sorted(names, key=len, reverse=True)
        if name.strip()
    ]
    if not parts:
        return None
    return re.compile(r"(?<![\w])(?:" + "|".join(parts) + r")(?![\w])", re.IGNORECASE)


def _guard_locations(raw: Any) -> list[dict[str, str | None]]:
    """Guardrail 2 (Phase 11c): objects only, cleaned/truncated city (empty -> dropped) and
    country (empty/non-string -> null), first-wins dedupe by `location_key`, at most 10."""
    out: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        city = _clean(item.get("city"), CITY_MAX)
        if not city:
            continue
        country = _clean(item.get("country"), COUNTRY_MAX) or None
        key = location_key(city, country)
        if key in seen:
            continue
        seen.add(key)
        out.append({"city": city, "country": country})
        if len(out) >= LOCATIONS_MAX:
            break
    return out


def _scrub_locations(locations: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """Guardrail 8 for locations: contacts removed; an item whose city is left empty is dropped;
    re-deduped since scrubbing can make two items equal."""
    out: list[dict[str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for loc in locations:
        city = collapse(_strip_contacts(loc["city"] or ""))
        if not city:
            continue
        country = collapse(_strip_contacts(loc["country"] or "")) or None
        key = location_key(city, country)
        if key not in seen:
            seen.add(key)
            out.append({"city": city, "country": country})
    return out


def _strip_contacts(text: str) -> str:
    text = _PHONE.sub("", _EMAIL.sub("", text))
    return re.sub(r"[ \t]{2,}", " ", text)


def _guard_partner(
    raw: Any, partners: list[PartnerRef]
) -> tuple[PartnerRef | None, dict[str, str | None] | None, str | None, str | None]:
    """-> (matched partner, suggested_partner, partner_display_name, organisation_name)."""
    from src.workshop0.services.partners import normalize_name

    raw = raw if isinstance(raw, dict) else {}
    org = _clean(raw.get("organisation_name"), PARTNER_NAME_MAX) or None
    suggested_display = _clean(raw.get("suggested_display_name"), PARTNER_NAME_MAX) or None

    matched: PartnerRef | None = None
    existing = raw.get("existing_partner_id")
    if isinstance(existing, int) and not isinstance(existing, bool):
        matched = next((p for p in partners if p.id == existing), None)
    if matched is None and org:
        key = normalize_name(org)[1]
        matched = next((p for p in partners if normalize_name(p.internal_name)[1] == key), None)

    suggested: dict[str, str | None] | None = None
    if matched is None and org:
        suggested = {"internal_name": normalize_name(org)[0][:PARTNER_NAME_MAX], "display_name": suggested_display}
    display = (matched.display_name if matched else None) or suggested_display
    return matched, suggested, display, org


def drafted_fields_of(draft: dict[str, Any]) -> list[str]:
    """The api.md group keys whose guarded value is non-empty, in contract order."""

    def filled(*keys: str) -> bool:
        return any(draft.get(k) not in (None, "", [], {}) for k in keys)

    groups = {
        "title": filled("title"),
        "type": filled("type"),
        "summary": filled("summary"),
        "description_md": filled("description_md"),
        "topics": filled("topic_slugs"),
        "location": filled("location_mode", "locations"),
        "dates": filled("starts_on", "ends_on"),
        "duration_text": filled("duration_text"),
        "deadline": filled("deadline_on"),
        "compensation": filled(
            "compensation_min",
            "compensation_max",
            "compensation_currency",
            "compensation_unit",
            "compensation_text",
        ),
        "partner": filled("partner_id", "suggested_partner"),
        "partner_display_name": filled("partner_display_name"),
        "internal_notes": filled("internal_notes"),
    }
    return [key for key in DRAFTED_FIELD_KEYS if groups[key]]


def guard_draft(
    content: Any,
    *,
    topics: list[TopicRef],
    partners: list[PartnerRef],
    keep_partner_identity: bool,
    today: date,
) -> dict[str, Any] | None:
    """Apply every deterministic guardrail in spec order; returns the api.md `draft` object, or
    None when title, summary and topics are all empty (the caller rejects)."""
    content = content if isinstance(content, dict) else {}

    # 1. text fields
    title = _clean(content.get("title"), TITLE_MAX)
    title = title if len(title) >= TITLE_MIN else ""
    summary = _clean(content.get("summary"), SUMMARY_MAX)
    description = _clean(content.get("description_md"), DESCRIPTION_MAX, multiline=True)
    duration_text = _clean(content.get("duration_text"), DURATION_MAX) or None
    internal_notes = _clean(content.get("internal_notes"), INTERNAL_NOTES_MAX, multiline=True) or None

    # 2. enums + locations
    type_ = _enum(content.get("type"), TYPES)
    location_mode = _enum(content.get("location_mode"), LOCATION_MODES)
    locations = [] if location_mode == "remote" else _guard_locations(content.get("locations"))

    # 3. topics
    topic_slugs = _guard_topics(content.get("topics"), {t.slug for t in topics})

    # 4. dates
    starts = _guard_date(content.get("starts_on"), today)
    ends = _guard_date(content.get("ends_on"), today)
    if starts is not None and ends is not None and ends < starts:
        ends = None
    deadline = _guard_date(content.get("deadline_on"), today)

    # 5. compensation
    compensation = _guard_compensation(content.get("compensation"))

    # 6. partner
    matched, suggested, partner_display_name, org = _guard_partner(content.get("partner"), partners)

    # 7. identity scrub (only when the admin did not ask to keep the partner's name)
    if not keep_partner_identity:
        names: set[str] = set()
        for source in (org, matched.internal_name if matched else None):
            if source:
                names.update(_name_variants(source))
        pattern = _scrub_pattern(names)
        if pattern is not None:
            replacement = partner_display_name or GENERIC_PARTNER
            title = pattern.sub(lambda _m: replacement, title)
            summary = pattern.sub(lambda _m: replacement, summary)
            description = pattern.sub(lambda _m: replacement, description)

    # 8. contact scrub, always (public fields only)
    title = " ".join(_strip_contacts(title).split())
    summary = " ".join(_strip_contacts(summary).split())
    description = _strip_contacts(description).strip()
    title = title if len(title) >= TITLE_MIN else ""
    locations = _scrub_locations(locations)

    # 9. rejection
    if not title and not summary and not topic_slugs:
        return None

    return {
        "title": title or None,
        "type": type_,
        "summary": summary or None,
        "description_md": description or None,
        "topic_slugs": topic_slugs,
        "location_mode": location_mode,
        "locations": locations,
        "starts_on": starts.isoformat() if starts else None,
        "ends_on": ends.isoformat() if ends else None,
        "duration_text": duration_text,
        "deadline_on": deadline.isoformat() if deadline else None,
        **compensation,
        "partner_id": matched.id if matched else None,
        "suggested_partner": suggested,
        "partner_display_name": partner_display_name,
        "internal_notes": internal_notes,
    }


# --------------------------------------------------------------------------- entry points


def draft_opportunity(
    text: str,
    *,
    topics: list[TopicRef],
    partners: list[PartnerRef],
    keep_partner_identity: bool,
    today: date,
) -> OpportunityDraftResult:
    """Pure: one LLM call + guardrails, no DB. Raises LLMUnavailable / LLMError /
    OpportunityDraftRejected."""
    from src.workshop0.config.settings import get_settings

    result = anthropic_client.call_json(
        system=_prompt("system"),
        user=build_user_prompt(
            text,
            topics=topics,
            partners=partners,
            keep_partner_identity=keep_partner_identity,
            today=today,
        ),
        tool_name=TOOL_NAME,
        input_schema=build_input_schema(topics),
        model=get_settings().workshop0_ai_network_model,
        max_tokens=MAX_TOKENS,
        timeout_s=TIMEOUT_S,
    )
    draft = guard_draft(
        result.content,
        topics=topics,
        partners=partners,
        keep_partner_identity=keep_partner_identity,
        today=today,
    )
    if draft is None:
        raise OpportunityDraftRejected(result, "no usable title, summary or topic in the model output")
    return OpportunityDraftResult(draft=draft, drafted_fields=drafted_fields_of(draft), llm=result)


def _log_failure(cause: str, exc: BaseException) -> None:
    status = cause.removeprefix("http_") if cause.startswith("http_") else None
    log.error(
        "ai.call_failed",
        purpose=PURPOSE,
        cause=cause,
        status=getattr(exc, "status", None) or status,
        request_id=getattr(exc, "request_id", None),
    )


def run_opportunity_draft(
    session: Session,
    *,
    text: str,
    opportunity_id: int | None,
    keep_partner_identity: bool,
) -> dict[str, Any]:
    """Endpoint helper -> the api.md response `data`. Records usage (success and rejection) and
    commits; maps failures to `ai_not_configured` 503 / `ai_draft_failed` 502."""
    from src.workshop0.ai.usage import record_usage
    from src.workshop0.db.models import Topic
    from src.workshop0.services import partners as partners_service

    topic_rows = session.scalars(
        select(Topic).where(Topic.active.is_(True)).order_by(Topic.position, Topic.id)
    ).all()
    topics = [TopicRef(t.slug, t.name, t.category) for t in topic_rows]
    partner_rows = sorted(partners_service.active_partners(session), key=lambda p: p.name_key)[:PARTNER_CAP]
    partners = [PartnerRef(p.id, p.internal_name, p.display_name) for p in partner_rows]
    today = datetime.now(timezone.utc).date()

    try:
        result = draft_opportunity(
            text,
            topics=topics,
            partners=partners,
            keep_partner_identity=keep_partner_identity,
            today=today,
        )
    except LLMUnavailable:
        raise api_error(
            "ai_not_configured",
            "AI drafting is not configured on this server. You can still fill the listing in by hand.",
            503,
        ) from None
    except LLMError as exc:
        _log_failure(exc.cause, exc)
        raise api_error("ai_draft_failed", "The draft could not be generated. Fill the listing in by hand or try again.", 502) from None
    except OpportunityDraftRejected as exc:
        _log_failure("guardrail_rejected", exc)
        record_usage(session, exc.llm, purpose=PURPOSE, opportunity_id=opportunity_id)
        session.commit()
        raise api_error("ai_draft_failed", "The draft could not be generated. Fill the listing in by hand or try again.", 502) from None

    row = record_usage(session, result.llm, purpose=PURPOSE, opportunity_id=opportunity_id)
    session.commit()
    return {
        "draft": result.draft,
        "drafted_fields": result.drafted_fields,
        "cost_usd": float(round(row.cost_usd, 6)),
        "model": result.llm.model,
    }
