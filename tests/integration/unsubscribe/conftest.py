import pytest


@pytest.fixture(autouse=True)
def _secret_and_no_smtp(monkeypatch):
    for name in ("HOST", "USER", "PASSWORD", "FROM"):
        monkeypatch.setenv(f"WORKSHOP0_SMTP_{name}", "")
    monkeypatch.setenv("WORKSHOP0_SESSION_SECRET", "unsub-test-secret-0123456789")
    monkeypatch.setenv("WORKSHOP0_BASE_URL", "http://base.test")
    import src.workshop0.config.settings as m

    m._settings = None
    yield
    m._settings = None
