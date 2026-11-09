"""Phase 11c location helpers (spec/data-model.md §Phase 11c).

Pure helpers shared by the opportunity service (validation, mirror, read rule) and the
drafter guardrail. No I/O.
"""

import json
from typing import TypedDict

CITY_MAX = 80
COUNTRY_MAX = 80
LOCATIONS_MAX = 10


class Location(TypedDict):
    city: str
    country: str | None


def collapse(text: str) -> str:
    """Trim and collapse internal whitespace to single spaces."""
    return " ".join(text.split())


def location_key(city: str, country: str | None) -> tuple[str, str]:
    """Return ``(collapse(city).casefold(), collapse(country or "").casefold())``."""
    return (collapse(city).casefold(), collapse(country or "").casefold())


def dedupe(locations: list[Location]) -> list[Location]:
    """Order-preserving dedupe by ``location_key``; first occurrence wins; every
    item is rebuilt with exactly ``city``/``country``."""
    seen: set[tuple[str, str]] = set()
    out: list[Location] = []
    for item in locations:
        key = location_key(item["city"], item.get("country"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"city": item["city"], "country": item.get("country")})
    return out


def parse_stored(locations_json: str | None, city: str | None, location_mode: str) -> list[Location]:
    """Read rule: parse ``locations_json``; a non-empty list is returned as is. If it is
    ``[]`` or unparseable, ``city`` is non-blank and the mode is not ``remote``, return
    ``[{"city": collapse(city), "country": None}]`` (a row written by revision 0007
    during the deploy overlap). Otherwise return ``[]``."""
    parsed: object = None
    if locations_json:
        try:
            parsed = json.loads(locations_json)
        except (TypeError, ValueError):
            parsed = None
    if isinstance(parsed, list) and parsed:
        items: list[Location] = []
        for item in parsed:
            if isinstance(item, dict) and isinstance(item.get("city"), str):
                country = item.get("country")
                items.append(
                    {"city": item["city"], "country": country if isinstance(country, str) else None}
                )
        if items:
            return items
    if city is not None and city.strip() and location_mode != "remote":
        return [{"city": collapse(city), "country": None}]
    return []


def dump(locations: list[Location]) -> str:
    """Return ``json.dumps(locations, ensure_ascii=False)``."""
    return json.dumps(locations, ensure_ascii=False)
