"""Phase 13: shared listing text for mail (used by opportunity.invite, alerts and the digest)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.workshop0.db.models import Opportunity, Partner
from src.workshop0.services import locations as loc

UNIT_LABEL = {"hour": "hour", "day": "day", "course": "course", "month": "month"}
CURRENCY_SYMBOL = {"INR": "₹", "USD": "$"}
DEFAULT_PARTNER = "a smallTech partner"


def compensation_text(opp: Opportunity) -> str:
    low, high = opp.compensation_min, opp.compensation_max
    if low is None and high is None:
        return opp.compensation_text or "To be discussed"
    symbol = CURRENCY_SYMBOL.get(opp.compensation_currency or "", (opp.compensation_currency or "") + " ")
    amount = f"{low:,}" if high is None or low == high else f"{low:,}–{high:,}" if low is not None else f"{high:,}"
    unit = f" per {UNIT_LABEL[opp.compensation_unit]}" if opp.compensation_unit in UNIT_LABEL else ""
    return f"{symbol}{amount}{unit}"


def listing_fields(session: Session, opportunity: Opportunity, base_url: str) -> dict:
    """Return {title, partner, compensation, cities, url}; display strings only."""
    from src.workshop0.services.opportunities import public_url

    partner = opportunity.partner_display_name
    if not partner and opportunity.partner_id is not None:
        found = session.get(Partner, opportunity.partner_id)
        partner = found.display_name if found is not None else None
    cities = [
        i["city"]
        for i in loc.parse_stored(opportunity.locations_json, opportunity.city, opportunity.location_mode)
    ]
    return {
        "title": opportunity.title,
        "partner": partner or DEFAULT_PARTNER,
        "compensation": compensation_text(opportunity),
        "cities": ", ".join(cities) if cities else opportunity.location_mode.capitalize(),
        "url": public_url(base_url, opportunity.slug),
    }
