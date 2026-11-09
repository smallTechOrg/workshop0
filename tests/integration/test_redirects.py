import pytest

from src.workshop0.api import LANDING_HTML


@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/admin", "/app/admin/"),
        ("/j/Ab3dEfGh", "/app/join/?s=Ab3dEfGh"),
        ("/p/some-participant-token", "/app/p/?t=some-participant-token"),
        ("/f/some-admin-token", "/app/f/?t=some-admin-token"),
        # The landing page has exactly one URL — the export root alias folds into `/`.
        ("/app", "/"),
        ("/app/", "/"),
        # Phase 10 — Opportunity Board pretty links.
        ("/opportunities", "/app/opportunities/"),
        ("/opportunities/12", "/app/opportunities/view/?id=12"),
    ],
)
def test_pretty_redirects_are_307_to_exact_targets(client, path, target):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == target


def test_root_serves_the_landing_page_html_when_the_export_is_built(
    client, monkeypatch, tmp_path
):
    """Deterministic in CI: point at a stand-in export so the built case always runs."""
    import src.workshop0.api as api_module

    landing = LANDING_HTML if LANDING_HTML.is_file() else tmp_path / "index.html"
    if landing != LANDING_HTML:
        landing.write_text("<!doctype html><html><body>landing</body></html>", encoding="utf-8")
    monkeypatch.setattr(api_module, "LANDING_HTML", landing)

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-cache"
    assert "<html" in response.text.lower()


def test_root_returns_503_when_the_export_is_missing(client, monkeypatch, tmp_path):
    """No `pnpm build` → a clear 503. It must NOT redirect to `/app/`, which
    now redirects back to `/` (that would be an infinite loop)."""
    import src.workshop0.api as api_module

    monkeypatch.setattr(api_module, "LANDING_HTML", tmp_path / "not-built" / "index.html")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 503
    assert "frontend not built" in response.text
    assert "location" not in response.headers


def test_opportunity_redirect_quotes_a_non_numeric_segment(client):
    """A non-numeric id is passed through URL-quoted; the page renders its not-found state."""
    response = client.get("/opportunities/a b&c", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app/opportunities/view/?id=a%20b%26c"
