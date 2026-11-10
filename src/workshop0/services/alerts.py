"""Phase 13: saved-search criteria and alert enqueue (api.md §Phase 13; one alert per user per listing)."""

from __future__ import annotations

import json
from collections import defaultdict

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, utcnow
from src.workshop0.db.models import AppUser, EmailOutbox, Opportunity, SavedSearch, Topic, TrainerProfile
from src.workshop0.email import outbox
from src.workshop0.services import email_prefs
from src.workshop0.services import locations as loc
from src.workshop0.services import unsubscribe
from src.workshop0.services.listing_text import listing_fields

log = structlog.get_logger("workshop0")

KEYS = ("types", "topic_slugs", "location_modes", "cities")
TYPES = ("workshop", "engagement", "role", "cofacilitation")
LOCATION_MODES = ("remote", "onsite", "hybrid")
TOPICS_MAX = 10
CITIES_MAX = 5
CITY_MAX = 80


def _bad(message: str):
    return api_error("validation_error", message, 422)


def _str_list(criteria: dict, key: str) -> list[str]:
    value = criteria.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise _bad(f"criteria.{key}: must be a list")
    if not all(isinstance(v, str) for v in value):
        raise _bad(f"criteria.{key}: every entry must be a string")
    return value


def _choices(criteria: dict, key: str, allowed: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for v in _str_list(criteria, key):
        if v not in allowed:
            raise _bad(f"criteria.{key}: unknown value {v[:40]!r}")
        if v not in out:
            out.append(v)
    return out


def validate_criteria(session: Session, criteria: dict) -> dict:
    """Return the normalised criteria (every key present) or raise 422 `validation_error`."""
    if not isinstance(criteria, dict):
        raise _bad("criteria: must be an object")
    unknown = [k for k in criteria if k not in KEYS]
    if unknown:
        raise _bad(f"criteria.{str(unknown[0])[:40]}: unknown key")
    types = _choices(criteria, "types", TYPES)
    modes = _choices(criteria, "location_modes", LOCATION_MODES)

    slugs = list(dict.fromkeys(_str_list(criteria, "topic_slugs")))
    if len(slugs) > TOPICS_MAX:
        raise _bad(f"criteria.topic_slugs: at most {TOPICS_MAX} topics")
    if slugs:
        known = set(session.scalars(select(Topic.slug).where(Topic.slug.in_(slugs))))
        missing = [s for s in slugs if s not in known]
        if missing:
            raise _bad(f"criteria.topic_slugs: unknown topic {missing[0][:48]!r}")

    cities: list[str] = []
    seen: set[str] = set()
    for raw in _str_list(criteria, "cities"):
        city = loc.collapse(raw)
        if not city or len(city) > CITY_MAX:
            raise _bad(f"criteria.cities: each city must be 1-{CITY_MAX} characters")
        if city.casefold() not in seen:
            seen.add(city.casefold())
            cities.append(city)
    if len(cities) > CITIES_MAX:
        raise _bad(f"criteria.cities: at most {CITIES_MAX} cities")

    out = {"types": types, "topic_slugs": slugs, "location_modes": modes, "cities": cities}
    if not any(out.values()):
        raise _bad("criteria: choose at least one filter")
    return out


def _city_key(city: str) -> str:
    return loc.collapse(city).casefold()


def matches(criteria: dict, opportunity: Opportunity, topic_slugs: frozenset[str]) -> bool:
    """Pure: every non-empty list must be satisfied; empty lists never exclude.
    (Effective-open gating is the caller's job; see `enqueue_alerts_for`.)"""
    types = criteria.get("types") or []
    if types and opportunity.type not in types:
        return False
    wanted = criteria.get("topic_slugs") or []
    if wanted and not (set(wanted) & topic_slugs):
        return False
    modes = criteria.get("location_modes") or []
    if modes and opportunity.location_mode not in modes:
        return False
    cities = criteria.get("cities") or []
    if cities:
        listing = {
            _city_key(i["city"])
            for i in loc.parse_stored(opportunity.locations_json, opportunity.city, opportunity.location_mode)
        }
        if not ({_city_key(c) for c in cities} & listing):
            return False
    return True


def enqueue_alerts_for(session: Session, opportunity: Opportunity, *, base_url: str) -> int:
    """One `network.alert` per consenting, opted-in user with a matching alerts-enabled saved
    search; returns the number of newly created outbox rows. Never commits."""
    from src.workshop0.services.opportunities import effective_status, topics_by_opportunity

    if effective_status(opportunity, utcnow()) != "open":
        return 0
    slugs = frozenset(t.slug for t in topics_by_opportunity(session, [opportunity.id]).get(opportunity.id, []))

    rows = session.execute(
        select(SavedSearch, AppUser)
        .join(AppUser, AppUser.id == SavedSearch.user_id)
        .join(TrainerProfile, TrainerProfile.user_id == SavedSearch.user_id)
        .where(SavedSearch.alerts_enabled.is_(True), TrainerProfile.consent_at.is_not(None))
        .order_by(SavedSearch.id)
    ).all()

    names: dict[int, list[str]] = defaultdict(list)
    users: dict[int, AppUser] = {}
    for search, user in rows:
        try:
            criteria = json.loads(search.criteria_json)
        except (TypeError, ValueError):
            continue
        if isinstance(criteria, dict) and matches(criteria, opportunity, slugs):
            names[user.id].append(search.name)
            users[user.id] = user
    if not users:
        return 0

    prefs = email_prefs.prefs_for(session, list(users))
    fields = listing_fields(session, opportunity, base_url)
    created = 0
    for user_id, user in users.items():
        if not prefs[user_id].alerts:
            continue
        key = f"alert:{opportunity.id}:{user_id}"
        existed = session.scalar(select(EmailOutbox.id).where(EmailOutbox.dedupe_key == key)) is not None
        outbox.enqueue(
            session,
            to=user.email,
            template="network.alert",
            context={
                "name": user.display_name,
                **fields,
                "search_names": ", ".join(names[user_id]),
                "unsubscribe_url": unsubscribe.url(base_url, user_id, "alerts"),
                "manage_url": f"{base_url}/app/network/searches/",
            },
            dedupe_key=key,
        )
        if not existed:
            created += 1
    return created
