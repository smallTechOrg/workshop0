"""Phase 13 templates: network.alert and network.digest, repeat sections, escaping."""

from src.workshop0.email.render import FOOTER, render

BASE = "http://base.test"


def _item(i, **kw):
    d = {"title": f"Job {i}", "partner": f"Partner {i}", "compensation": "INR 1 per day",
         "cities": ["Pune", "Goa"], "url": f"{BASE}/opportunities/job-{i}"}
    d.update(kw)
    return d


def _digest(n, more=0, **kw):
    return {"name": "Asha", "count": n + more, "listings": [_item(i) for i in range(n)], "more": more,
            "board_url": f"{BASE}/app/opportunities/", "unsubscribe_url": f"{BASE}/api/email/unsubscribe?t=abc",
            "manage_url": f"{BASE}/app/network/searches/", **kw}


ALERT = {"name": "Asha", "title": "GenAI <i>Workshop</i>", "partner": "Acme", "compensation": "INR 5000 per day",
         "cities": ["Pune", "Goa"], "url": f"{BASE}/opportunities/genai", "search_names": "Pune, AI",
         "unsubscribe_url": f"{BASE}/api/email/unsubscribe?t=abc", "manage_url": f"{BASE}/app/network/searches/"}


def test_alert_content_and_subject():
    r = render("network.alert", ALERT)
    assert r.subject == "New opportunity: GenAI <i>Workshop</i>"
    for frag in ("Acme", "INR 5000 per day", "Pune, Goa", f"{BASE}/opportunities/genai",
                 "Matches your saved search: Pune, AI", f"{BASE}/api/email/unsubscribe?t=abc",
                 f"{BASE}/app/network/searches/"):
        assert frag in r.text
    assert r.text.count(FOOTER) == 1 and r.html.count(FOOTER) == 1
    assert "<img" not in r.html.lower() and "{{" not in r.html + r.text


def test_alert_html_escapes():
    r = render("network.alert", ALERT)
    assert "GenAI &lt;i&gt;Workshop&lt;/i&gt;" in r.html
    assert "<i>" not in r.html


def test_alert_empty_context():
    r = render("network.alert", {})
    assert "{{" not in r.text and "Hi there" in r.text


def test_digest_repeats_items():
    r = render("network.digest", _digest(3))
    assert r.subject == "Your Workshop0 digest: 3 new opportunities"
    for i in range(3):
        assert f"Job {i}" in r.text and f"{BASE}/opportunities/job-{i}" in r.html
    assert "more on the board" not in r.text and "more on the" not in r.html
    assert "Unsubscribe" in r.text and "Manage" in r.text
    assert r.text.count(FOOTER) == 1 and r.html.count(FOOTER) == 1


def test_digest_more_line():
    r = render("network.digest", _digest(10, more=4))
    assert "+4 more on the board" in r.text
    assert f'href="{BASE}/app/opportunities/"' in r.html
    assert r.subject.endswith("14 new opportunities")


def test_digest_zero_items_and_missing_list():
    assert "Job" not in render("network.digest", _digest(0)).text
    r = render("network.digest", {})
    assert "{{" not in r.text + r.html and "{#" not in r.text


def test_digest_item_escaping_and_outer_fallback():
    ctx = _digest(1)
    ctx["listings"] = [{"title": '</li><script>x</script>"&', "partner": "P", "url": f"{BASE}/o/1"}]
    r = render("network.digest", ctx)
    assert "<script>" not in r.html
    assert "&lt;script&gt;" in r.html and "&amp;" in r.html
    # item lacks compensation/cities -> renders empty, no leak of other items or placeholders
    assert "{{" not in r.html


def test_item_variable_beats_outer_context():
    ctx = _digest(1, title="OUTER")
    r = render("network.digest", ctx)
    assert "Job 0" in r.text and "OUTER" not in r.text


def test_no_cross_item_bleed():
    ctx = _digest(2)
    ctx["listings"][1]["partner"] = ""
    r = render("network.digest", ctx)
    assert "Partner 0" in r.text and "Partner 1" not in r.text
