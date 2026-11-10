"""Template rendering: subject from line 1, text + html, one footer, absolute links, no images."""

import pytest

from src.workshop0.email.render import FOOTER, TEMPLATES, render

CTX = {
    "name": "Asha <b>",
    "title": "GenAI workshop",
    "partner": "Acme",
    "compensation": "INR 5000 per day",
    "cities": ["Pune", "Bengaluru"],
    "url": "http://base.test/opportunities/genai-workshop",
    "applications_url": "http://base.test/app/network/applications/",
    "invite_url": "http://base.test/invite/tok",
    "expires_at": "2026-12-01",
    "status": "not_selected",
    "search_names": "Pune workshops",
    "unsubscribe_url": "http://base.test/api/email/unsubscribe?t=x",
    "manage_url": "http://base.test/app/network/searches/",
    "board_url": "http://base.test/app/opportunities/",
    "count": 1,
    "more": 0,
    "listings": [{"title": "T", "partner": "P", "compensation": "C", "cities": ["Pune"], "url": "http://base.test/opportunities/t"}],
}


def test_templates_exact_set():
    assert set(TEMPLATES) == {
        "network.welcome",
        "network.invite",
        "opportunity.invite",
        "application.received",
        "application.status_changed",
        "network.alert",
        "network.digest",
    }


@pytest.mark.parametrize("template", TEMPLATES)
def test_every_template_renders_text_html_one_footer(template):
    r = render(template, CTX)
    assert r.subject and "\n" not in r.subject and "{{" not in r.subject
    assert "{{" not in r.text and "{{" not in r.html
    assert r.text.count(FOOTER) == 1 and r.html.count(FOOTER) == 1
    assert "<img" not in r.html.lower()
    assert "http://base.test/" in r.text and 'href="http://base.test/' in r.html
    assert "<b>" not in r.html.replace("<strong>", "").replace("</strong>", "").split("Asha")[1][:6]


def test_html_escapes_context_and_lists_join():
    r = render("opportunity.invite", CTX)
    assert "Asha &lt;b&gt;" in r.html
    assert "Pune, Bengaluru" in r.text
    assert "INR 5000 per day" in r.text


def test_status_label_and_default_name():
    r = render("application.status_changed", {**CTX, "name": ""})
    assert "Not selected" in r.text and "Hi there" in r.text


def test_unknown_template_is_an_error():
    with pytest.raises(ValueError):
        render("nope", {})


def test_empty_context_renders_without_crashing():
    for t in TEMPLATES:
        assert render(t, {}).text
