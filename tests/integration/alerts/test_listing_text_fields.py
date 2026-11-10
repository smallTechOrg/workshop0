from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.workshop0.db.models import Opportunity, Partner
from src.workshop0.db.session import create_db_session
from src.workshop0.services.listing_text import listing_fields

BASE = "http://base.test"


def _o(**kw):
    d = dict(
        slug="s-1", title="T", type="role", summary="s", location_mode="onsite", city="Pune",
        locations_json=json.dumps([{"city": "Pune", "country": "India"}, {"city": "Goa", "country": None}]),
        status="open", deadline=datetime.now(timezone.utc) + timedelta(days=2),
    )
    d.update(kw)
    return Opportunity(**d)


def test_fields_and_keys():
    with create_db_session() as s:
        f = listing_fields(s, _o(partner_display_name="Disp", partner_internal_name="Internal Co"), BASE)
    assert set(f) == {"title", "partner", "compensation", "cities", "url"}
    assert f["partner"] == "Disp" and f["cities"] == "Pune, Goa" and f["url"] == f"{BASE}/opportunities/s-1"
    assert f["compensation"] == "To be discussed"
    assert "Internal" not in json.dumps(f)


def test_default_partner_remote_and_compensation_variants():
    with create_db_session() as s:
        f = listing_fields(s, _o(location_mode="remote", city=None, locations_json="[]"), BASE)
        assert f["partner"] == "a smallTech partner" and f["cities"] == "Remote"
        f = listing_fields(s, _o(compensation_text="Negotiable"), BASE)
        assert f["compensation"] == "Negotiable"
        f = listing_fields(s, _o(compensation_min=100, compensation_max=100, compensation_currency="USD",
                                 compensation_unit="hour"), BASE)
        assert f["compensation"] == "$100 per hour"
        f = listing_fields(s, _o(compensation_min=None, compensation_max=900, compensation_currency="INR"), BASE)
        assert f["compensation"] == "₹900"


def test_partner_display_name_falls_back_to_partner_row():
    with create_db_session() as s:
        p = Partner(display_name="Partner Disp", internal_name="Partner Internal", name_key="partner internal")
        s.add(p)
        s.flush()
        f = listing_fields(s, _o(partner_id=p.id), BASE)
        assert f["partner"] == "Partner Disp"
