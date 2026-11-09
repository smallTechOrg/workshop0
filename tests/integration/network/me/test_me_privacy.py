"""Privacy (gate): rates, email and CV fields appear in no non-admin payload except the owner's
own GET /api/me/profile — asserted on serialized JSON."""

from __future__ import annotations

import json

from me_helpers import MULTI_LINE_CV, full_profile_body

RATE_MIN, RATE_MAX = 987_651, 987_659  # sentinels nothing else would produce
CV_SENTINEL = "ZZ-CV-SENTINEL-4b2e"
OWNER_EMAIL = "private.owner@example.test"
RATE_KEYS = ('"rate_min"', '"rate_max"', '"rate_currency"', '"rate_unit"')
CV_KEYS = ('"text_extract"', '"storage_key"', '"sha256"', '"cv"')


def _owner(make_user, signed_in_client, monkeypatch):
    from src.workshop0.ai import profile_draft

    monkeypatch.setattr(profile_draft, "run_profile_draft", lambda _id: None)  # no drafting needed
    user = make_user(OWNER_EMAIL)
    client = signed_in_client(user)
    pasted = client.post("/api/me/cv/text", json={"text": MULTI_LINE_CV + CV_SENTINEL})
    assert pasted.status_code == 200, pasted.text
    created = client.post("/api/me/profile", json=full_profile_body(rate_min=RATE_MIN, rate_max=RATE_MAX))
    assert created.status_code == 200, created.text
    return user, client, pasted


def _assert_clean(body: str, where: str) -> None:
    for needle in (str(RATE_MIN), str(RATE_MAX), OWNER_EMAIL, CV_SENTINEL, *RATE_KEYS, '"text_extract"',
                   '"storage_key"', '"sha256"'):
        assert needle not in body, f"{needle} leaked in {where}"


def test_owner_profile_is_the_only_payload_with_rates_email_and_cv(
    make_user, signed_in_client, client, monkeypatch, create_opportunity
):
    _, owner, pasted = _owner(make_user, signed_in_client, monkeypatch)
    create_opportunity(("python",), status="open")

    own = owner.get("/api/me/profile").text
    for needle in (str(RATE_MIN), str(RATE_MAX), OWNER_EMAIL, *RATE_KEYS, '"cv"'):
        assert needle in own
    # even the owner's payload never carries the raw extract or storage internals
    assert CV_SENTINEL not in own and '"text_extract"' not in own and '"storage_key"' not in own

    # the upload response: CV meta only, never text/keys/hash
    assert set(pasted.json()["data"]["cv"]) == {"id", "source", "original_filename", "draft_status"}
    _assert_clean(pasted.text, "POST /api/me/cv/text")
    draft = owner.get("/api/me/cv/draft").text
    assert CV_SENTINEL not in draft and '"text_extract"' not in draft and OWNER_EMAIL not in draft

    # anonymous public surfaces
    for path in ("/api/public/topics", "/api/public/opportunities", "/api/health", "/api/auth/config",
                 "/api/auth/me"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        _assert_clean(response.text, path)
    [card] = client.get("/api/public/opportunities").json()["data"]["opportunities"]
    _assert_clean(client.get(f"/api/public/opportunities/{card['id']}").text, "public opportunity detail")

    # another signed-in trainer sees nothing of the owner on any /api/me read
    stranger = signed_in_client(make_user("stranger@example.test"))
    for path in ("/api/me/profile", "/api/me/cv/draft", "/api/me/cv/file", "/api/auth/me"):
        _assert_clean(stranger.get(path).text, f"stranger {path}")


def test_owner_auth_me_carries_no_rates_or_cv(make_user, signed_in_client, monkeypatch):
    _, owner, _ = _owner(make_user, signed_in_client, monkeypatch)
    body = owner.get("/api/auth/me").text
    payload = json.loads(body)
    assert payload.get("data", payload)["user"]["has_profile"] is True
    for needle in (str(RATE_MIN), str(RATE_MAX), CV_SENTINEL, *RATE_KEYS, *CV_KEYS):
        assert needle not in body, needle
