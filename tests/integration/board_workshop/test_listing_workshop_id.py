"""A2: admin-only `workshop_id` on cofacilitation listings; never in public payloads."""

import json

from sqlalchemy import text

from src.workshop0.db.session import create_db_session
from tests.conftest import opportunity_body


def _body(topic_ids, **kw):
    return opportunity_body([topic_ids["generative-ai"]], type="cofacilitation", **kw)


def _audit(oid):
    with create_db_session() as s:
        rows = s.execute(text(
            "SELECT detail_json FROM facilitator_action WHERE subject_type='opportunity' "
            "AND subject_id=:i ORDER BY id"), {"i": oid}).all()
    return [json.loads(r[0]) for r in rows]


def test_create_with_workshop_returns_it_in_admin_payloads(client, admin_headers, topic_ids, workshop):
    r = client.post("/api/admin/opportunities", headers=admin_headers,
                    json=_body(topic_ids, workshop_id=workshop["id"]))
    assert r.status_code == 200, r.text
    opp = r.json()["data"]["opportunity"]
    assert opp["workshop_id"] == workshop["id"]
    got = client.get(f"/api/admin/opportunities/{opp['id']}", headers=admin_headers).json()["data"]["opportunity"]
    assert got["workshop_id"] == workshop["id"]
    lst = client.get("/api/admin/opportunities", headers=admin_headers).json()["data"]
    row = next(o for o in lst["opportunities"] if o["id"] == opp["id"])
    assert row["workshop_id"] == workshop["id"]
    assert "workshop_id" in _audit(opp["id"])[0]["changed_fields"]


def test_default_is_null(client, admin_headers, topic_ids):
    r = client.post("/api/admin/opportunities", headers=admin_headers, json=_body(topic_ids))
    assert r.json()["data"]["opportunity"]["workshop_id"] is None


def test_unknown_workshop_is_422(client, admin_headers, topic_ids):
    for bad in (999999, 0, -3, 2**40):
        r = client.post("/api/admin/opportunities", headers=admin_headers, json=_body(topic_ids, workshop_id=bad))
        assert r.status_code == 422, (bad, r.text)
        assert r.json()["detail"]["code"] == "validation_error"
    r = client.post("/api/admin/opportunities", headers=admin_headers, json=_body(topic_ids, workshop_id="3"))
    assert r.status_code == 422


def test_non_cofacilitation_type_with_workshop_is_422(client, admin_headers, topic_ids, workshop):
    r = client.post("/api/admin/opportunities", headers=admin_headers,
                    json=opportunity_body([topic_ids["generative-ai"]], type="workshop", workshop_id=workshop["id"]))
    assert r.status_code == 422
    assert "workshop_id: only for co-facilitation listings" in json.dumps(r.json())


def test_changing_type_away_while_set_is_422_and_unset_together_is_ok(client, admin_headers, topic_ids, workshop):
    opp = client.post("/api/admin/opportunities", headers=admin_headers,
                      json=_body(topic_ids, workshop_id=workshop["id"])).json()["data"]["opportunity"]
    url = f"/api/admin/opportunities/{opp['id']}"
    r = client.patch(url, json={"type": "role"}, headers=admin_headers)
    assert r.status_code == 422
    assert "only for co-facilitation" in json.dumps(r.json())
    r = client.patch(url, json={"type": "role", "workshop_id": None}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["opportunity"]["workshop_id"] is None


def test_patch_set_clear_and_noop_audit(client, admin_headers, topic_ids, workshop):
    opp = client.post("/api/admin/opportunities", headers=admin_headers, json=_body(topic_ids)).json()["data"]["opportunity"]
    url = f"/api/admin/opportunities/{opp['id']}"
    assert client.patch(url, json={"workshop_id": workshop["id"]}, headers=admin_headers).status_code == 200
    n = len(_audit(opp["id"]))
    assert _audit(opp["id"])[-1]["changed_fields"] == ["workshop_id"]
    assert client.patch(url, json={"workshop_id": workshop["id"]}, headers=admin_headers).status_code == 200
    assert len(_audit(opp["id"])) == n  # no-op writes no audit row
    r = client.patch(url, json={"workshop_id": None}, headers=admin_headers)
    assert r.json()["data"]["opportunity"]["workshop_id"] is None
    assert len(_audit(opp["id"])) == n + 1
    assert client.patch(url, json={"workshop_id": 999999}, headers=admin_headers).status_code == 422


def test_workshop_id_never_in_public_payloads_or_seo(client, admin_headers, topic_ids, workshop, monkeypatch, tmp_path):
    import src.workshop0.api.seo as seo_api

    # The backend CI job has no built frontend; give the SEO route a minimal template.
    view = tmp_path / "view.html"
    view.write_text("<!DOCTYPE html><html><head><title>x</title></head><body></body></html>", encoding="utf-8")
    monkeypatch.setattr(seo_api, "VIEW_HTML", view)
    opp = client.post("/api/admin/opportunities", headers=admin_headers,
                      json=_body(topic_ids, workshop_id=workshop["id"], status="open")).json()["data"]["opportunity"]
    needle_id = f'"workshop_id"'
    lst = client.get("/api/public/opportunities")
    det = client.get(f"/api/public/opportunities/{opp['slug']}")
    assert lst.status_code == 200 and det.status_code == 200
    for resp in (lst, det):
        assert needle_id not in resp.text and "workshop_id" not in resp.text
    for path in (f"/opportunities/{opp['slug']}", "/sitemap.xml"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 200, path
        assert "workshop_id" not in resp.text
        assert workshop["admin_token"] not in resp.text if "admin_token" in workshop else True
