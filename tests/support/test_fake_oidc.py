"""Self-test for the local OIDC issuer (tests/support/fake_oidc.py).

Runs the in-process issuer and the CLI (as a real subprocess on a free port). Set
FAKE_OIDC_URL to additionally check an already-running instance.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
import pytest

from tests.support.fake_oidc import (
    KID,
    ROGUE_KID,
    WRONG_AUD,
    WRONG_ISS,
    authorize_redirect,
    run_in_thread,
    subject_for,
)

CLIENT_ID = "test-client"
REDIRECT_URI = "http://localhost:8001/api/auth/google/callback"
SCRIPT = Path(__file__).with_name("fake_oidc.py")


@pytest.fixture(scope="module")
def issuer():
    srv = run_in_thread()
    yield srv
    srv.stop()


@pytest.fixture(autouse=True)
def _clear_flags(issuer):
    issuer.reset()
    yield
    issuer.reset()


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _authorize_params(**extra: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "state": secrets.token_urlsafe(12),
        "nonce": secrets.token_urlsafe(12),
    }
    params.update(extra)
    return params


def _verify(token: str, base_url: str, issuer_claim: str, *, nonce: str | None = None) -> dict:
    """Verify an ID token the way the app does: JWKS by kid, RS256, iss, aud, exp (60 s leeway)."""
    jwks = httpx.get(f"{base_url}/jwks").json()
    kid = jwt.get_unverified_header(token)["kid"]
    matches = [k for k in jwks["keys"] if k["kid"] == kid]
    if not matches:
        raise LookupError(f"kid {kid!r} not in JWKS")
    key = jwt.PyJWK(matches[0]).key
    claims = jwt.decode(token, key, algorithms=["RS256"], audience=CLIENT_ID, issuer=issuer_claim, leeway=60)
    if nonce is not None and claims.get("nonce") != nonce:
        raise ValueError("nonce mismatch")
    return claims


def _sign_in(base_url: str, email: str, *, pkce: bool = True, **extra: str) -> tuple[dict, dict]:
    """authorize (login_hint) -> token. Returns (token response JSON, authorize params)."""
    verifier, challenge = _pkce()
    params = _authorize_params(**extra)
    if pkce:
        params.update(code_challenge=challenge, code_challenge_method="S256")
    params["login_hint"] = email
    resp = httpx.get(f"{base_url}/authorize", params=params, follow_redirects=False)
    assert resp.status_code == 302, resp.text
    back = parse_qs(urlsplit(resp.headers["location"]).query)
    assert back["state"] == [params["state"]]
    form = {"grant_type": "authorization_code", "code": back["code"][0], "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID, "client_secret": "test-secret"}
    if pkce:
        form["code_verifier"] = verifier
    tok = httpx.post(f"{base_url}/token", data=form)
    assert tok.status_code == 200, tok.text
    return tok.json(), params


# --- happy path --------------------------------------------------------------------------


def test_discovery_document(issuer):
    doc = httpx.get(f"{issuer.base_url}/.well-known/openid-configuration").json()
    assert doc["issuer"] == issuer.base_url == f"http://localhost:{issuer.port}"
    assert doc["authorization_endpoint"] == f"{issuer.base_url}/authorize"
    assert doc["token_endpoint"] == f"{issuer.base_url}/token"
    assert doc["jwks_uri"] == f"{issuer.base_url}/jwks"
    assert doc["userinfo_endpoint"] == f"{issuer.base_url}/userinfo"
    assert "RS256" in doc["id_token_signing_alg_values_supported"]
    assert "S256" in doc["code_challenge_methods_supported"]
    jwks = httpx.get(doc["jwks_uri"]).json()
    assert [(k["kid"], k["kty"], k["alg"]) for k in jwks["keys"]] == [(KID, "RSA", "RS256")]


def test_full_browser_flow_through_the_form_with_pkce(issuer):
    verifier, challenge = _pkce()
    params = _authorize_params(code_challenge=challenge, code_challenge_method="S256")
    page = httpx.get(f"{issuer.base_url}/authorize", params=params)
    assert page.status_code == 200
    assert 'id="email"' in page.text and 'name="email"' in page.text
    assert '<label for="email">Email</label>' in page.text
    assert ">Sign in</button>" in page.text

    # Submit the form exactly as a browser would (hidden fields + email).
    form = {k: v for k, v in params.items()}
    form["email"] = "Trainer.One@example.test"
    resp = httpx.post(f"{issuer.base_url}/authorize", data=form, follow_redirects=False)
    assert resp.status_code == 302
    loc = urlsplit(resp.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == REDIRECT_URI
    back = parse_qs(loc.query)
    assert back["state"] == [params["state"]]

    tok = httpx.post(
        f"{issuer.base_url}/token",
        data={"grant_type": "authorization_code", "code": back["code"][0], "redirect_uri": REDIRECT_URI, "code_verifier": verifier},
        auth=(CLIENT_ID, "test-secret"),  # client_secret_basic
    )
    assert tok.status_code == 200, tok.text
    body = tok.json()
    assert body["token_type"] == "Bearer" and body["access_token"]
    claims = _verify(body["id_token"], issuer.base_url, issuer.issuer, nonce=params["nonce"])
    assert claims["iss"] == issuer.base_url
    assert claims["aud"] == CLIENT_ID
    assert claims["email"] == "Trainer.One@example.test"
    assert claims["email_verified"] is True
    assert claims["sub"] == subject_for("trainer.one@example.test")
    assert claims["name"] == "Trainer One"
    assert claims["picture"].startswith(f"{issuer.base_url}/avatar/")
    assert claims["exp"] - claims["iat"] == 3600
    assert abs(claims["iat"] - time.time()) < 10
    assert httpx.get(claims["picture"]).headers["content-type"] == "image/svg+xml"

    info = httpx.get(f"{issuer.base_url}/userinfo", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert info.status_code == 200
    assert info.json()["email"] == "Trainer.One@example.test"
    assert info.json()["sub"] == claims["sub"]


def test_sub_is_stable_per_email_and_distinct_between_emails(issuer):
    a1, _ = _sign_in(issuer.base_url, "same@example.test")
    a2, _ = _sign_in(issuer.base_url, "SAME@example.test")
    b, _ = _sign_in(issuer.base_url, "other@example.test")
    sub = lambda t: jwt.decode(t["id_token"], options={"verify_signature": False})["sub"]  # noqa: E731
    assert sub(a1) == sub(a2)
    assert sub(a1) != sub(b)


def test_authorize_redirect_helper_and_email_query_skip_the_form(issuer):
    params = _authorize_params()
    url = f"{issuer.base_url}/authorize?{urlencode(params)}"
    target = authorize_redirect(url, "helper@example.test")
    assert target.startswith(REDIRECT_URI + "?")
    assert parse_qs(urlsplit(target).query)["state"] == [params["state"]]

    resp = httpx.get(f"{issuer.base_url}/authorize", params={**params, "email": "q@example.test"}, follow_redirects=False)
    assert resp.status_code == 302 and "code=" in resp.headers["location"]


def test_cli_subprocess_serves_the_protocol(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPT), "--port", str(port), "--quiet", "--unverified"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base = f"http://localhost:{port}"
    try:
        for _ in range(100):
            try:
                doc = httpx.get(f"{base}/.well-known/openid-configuration", timeout=1).json()
                break
            except httpx.TransportError:
                time.sleep(0.1)
        else:
            pytest.fail(f"fake_oidc CLI did not start: {proc.stderr.read1().decode() if proc.poll() is not None else ''}")
        assert doc["issuer"] == base
        tok, params = _sign_in(base, "cli@example.test")
        claims = _verify(tok["id_token"], base, base, nonce=params["nonce"])
        assert claims["email_verified"] is False  # --unverified applies to every token
        assert httpx.get(f"{base}/_control").json()["flags"] == ["unverified"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_issuer_override_sets_iss_and_discovery():
    with run_in_thread(issuer="http://localhost:9999/") as srv:
        doc = httpx.get(f"{srv.base_url}/.well-known/openid-configuration").json()
        assert doc["issuer"] == "http://localhost:9999"
        tok, _ = _sign_in(srv.base_url, "o@example.test")
        assert _verify(tok["id_token"], srv.base_url, "http://localhost:9999")["iss"] == "http://localhost:9999"


@pytest.mark.skipif(not os.environ.get("FAKE_OIDC_URL"), reason="no external FAKE_OIDC_URL instance given")
def test_external_running_instance():
    base = os.environ["FAKE_OIDC_URL"].rstrip("/")
    doc = httpx.get(f"{base}/.well-known/openid-configuration").json()
    tok, params = _sign_in(base, "live@example.test")
    assert _verify(tok["id_token"], base, doc["issuer"], nonce=params["nonce"])["email"] == "live@example.test"


# --- edge cases: negative-case tokens ---------------------------------------------------


@pytest.mark.parametrize(
    "email, expected_exc",
    [
        ("wrongaud+a@example.test", jwt.InvalidAudienceError),
        ("a+expired@example.test", jwt.ExpiredSignatureError),
        ("badsig+a@example.test", jwt.InvalidSignatureError),
        ("unknownkid+a@example.test", LookupError),
        ("wrongiss+a@example.test", jwt.InvalidIssuerError),
        ("badnonce+a@example.test", ValueError),
    ],
)
def test_magic_email_tags_produce_tokens_the_app_must_refuse(issuer, email, expected_exc):
    tok, params = _sign_in(issuer.base_url, email)
    with pytest.raises(expected_exc):
        _verify(tok["id_token"], issuer.base_url, issuer.issuer, nonce=params["nonce"])
    claims = jwt.decode(tok["id_token"], options={"verify_signature": False})
    assert claims["email"] == email  # address exactly as typed


def test_magic_email_details(issuer):
    tok, params = _sign_in(issuer.base_url, "unverified+t1@example.test")
    claims = _verify(tok["id_token"], issuer.base_url, issuer.issuer, nonce=params["nonce"])
    assert claims["email_verified"] is False

    exp = jwt.decode(_sign_in(issuer.base_url, "x+expired@example.test")[0]["id_token"], options={"verify_signature": False})
    assert exp["exp"] < time.time() - 3000  # well beyond the app's 60 s leeway
    assert jwt.decode(_sign_in(issuer.base_url, "wrongaud+x@example.test")[0]["id_token"], options={"verify_signature": False})["aud"] == WRONG_AUD
    assert jwt.decode(_sign_in(issuer.base_url, "wrongiss+x@example.test")[0]["id_token"], options={"verify_signature": False})["iss"] == WRONG_ISS
    assert jwt.get_unverified_header(_sign_in(issuer.base_url, "badsig+x@example.test")[0]["id_token"])["kid"] == KID
    assert jwt.get_unverified_header(_sign_in(issuer.base_url, "unknownkid+x@example.test")[0]["id_token"])["kid"] == ROGUE_KID

    # A tag-like word that is not a whole segment does nothing.
    plain = _sign_in(issuer.base_url, "notexpired@example.test")[0]
    assert _verify(plain["id_token"], issuer.base_url, issuer.issuer)["email_verified"] is True


def test_control_endpoint_sets_and_resets_issuer_wide_flags(issuer):
    r = httpx.post(f"{issuer.base_url}/_control", json={"flags": {"expired": True, "unverified": True}})
    assert r.status_code == 200 and r.json()["flags"] == ["expired", "unverified"]
    tok, _ = _sign_in(issuer.base_url, "plain@example.test")
    claims = jwt.decode(tok["id_token"], options={"verify_signature": False})
    assert claims["email_verified"] is False and claims["exp"] < time.time()

    assert httpx.post(f"{issuer.base_url}/_control", json={"flags": {"wrong_aud": True}, "replace": True}).json()["flags"] == ["wrong_aud"]
    assert httpx.post(f"{issuer.base_url}/_control/reset").json()["flags"] == []
    tok, params = _sign_in(issuer.base_url, "plain@example.test")
    assert _verify(tok["id_token"], issuer.base_url, issuer.issuer, nonce=params["nonce"])["email_verified"] is True


def test_flags_fixed_at_code_issue_and_query_and_checkbox_flags(issuer):
    # Flag on while the code is minted, cleared before exchange -> token still carries it.
    issuer.set_flags(unverified=True)
    params = _authorize_params(login_hint="fixed@example.test")
    loc = httpx.get(f"{issuer.base_url}/authorize", params=params, follow_redirects=False).headers["location"]
    issuer.reset()
    code = parse_qs(urlsplit(loc).query)["code"][0]
    tok = httpx.post(f"{issuer.base_url}/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID}).json()
    assert jwt.decode(tok["id_token"], options={"verify_signature": False})["email_verified"] is False

    tok, _ = _sign_in(issuer.base_url, "q@example.test", flags="wrong_aud")
    assert jwt.decode(tok["id_token"], options={"verify_signature": False})["aud"] == WRONG_AUD

    form = {**_authorize_params(), "email": "box@example.test", "flag": "unverified"}
    loc = httpx.post(f"{issuer.base_url}/authorize", data=form, follow_redirects=False).headers["location"]
    code = parse_qs(urlsplit(loc).query)["code"][0]
    tok = httpx.post(f"{issuer.base_url}/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID}).json()
    assert jwt.decode(tok["id_token"], options={"verify_signature": False})["email_verified"] is False


def test_no_nonce_requested_means_no_nonce_claim(issuer):
    params = _authorize_params()
    del params["nonce"], params["state"]
    resp = httpx.get(f"{issuer.base_url}/authorize", params={**params, "login_hint": "n@example.test"}, follow_redirects=False)
    back = parse_qs(urlsplit(resp.headers["location"]).query)
    assert "state" not in back
    tok = httpx.post(f"{issuer.base_url}/token", data={"grant_type": "authorization_code", "code": back["code"][0], "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID}).json()
    assert "nonce" not in _verify(tok["id_token"], issuer.base_url, issuer.issuer)


def test_mint_id_token_helper(issuer):
    token = issuer.mint_id_token(email="m@example.test", aud=CLIENT_ID, nonce="n1")
    assert _verify(token, issuer.base_url, issuer.issuer, nonce="n1")["email"] == "m@example.test"
    with pytest.raises(jwt.InvalidSignatureError):
        _verify(issuer.mint_id_token(email="m@example.test", aud=CLIENT_ID, flags={"bad_signature"}), issuer.base_url, issuer.issuer)


# --- error paths -------------------------------------------------------------------------


def _code_for(issuer, email: str = "e@example.test", **extra: str) -> str:
    params = _authorize_params(login_hint=email, **extra)
    loc = httpx.get(f"{issuer.base_url}/authorize", params=params, follow_redirects=False).headers["location"]
    return parse_qs(urlsplit(loc).query)["code"][0]


def _exchange(issuer, **form: str) -> httpx.Response:
    base = {"grant_type": "authorization_code", "redirect_uri": REDIRECT_URI, "client_id": CLIENT_ID}
    return httpx.post(f"{issuer.base_url}/token", data={**base, **form})


def test_code_is_single_use(issuer):
    code = _code_for(issuer)
    assert _exchange(issuer, code=code).status_code == 200
    again = _exchange(issuer, code=code)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


def test_token_errors(issuer):
    assert _exchange(issuer, code="nope").json()["error"] == "invalid_grant"
    assert _exchange(issuer, code=_code_for(issuer), redirect_uri="http://localhost:8001/other").json()["error"] == "invalid_grant"
    assert _exchange(issuer, code=_code_for(issuer), client_id="someone-else").json()["error"] == "invalid_grant"
    assert _exchange(issuer, code=_code_for(issuer), grant_type="password").json()["error"] == "unsupported_grant_type"
    assert _exchange(issuer, code="").json()["error"] == "invalid_request"
    r = httpx.post(f"{issuer.base_url}/token", data={"grant_type": "authorization_code", "code": _code_for(issuer), "redirect_uri": REDIRECT_URI})
    assert r.status_code == 401 and r.json()["error"] == "invalid_client"


def test_pkce_is_enforced_when_a_challenge_was_sent(issuer):
    verifier, challenge = _pkce()
    code = _code_for(issuer, code_challenge=challenge, code_challenge_method="S256")
    bad = _exchange(issuer, code=code, code_verifier=verifier + "x")
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_grant"

    code = _code_for(issuer, code_challenge=challenge, code_challenge_method="S256")
    missing = _exchange(issuer, code=code)
    assert missing.status_code == 400 and "code_verifier" in missing.json()["error_description"]

    code = _code_for(issuer, code_challenge=challenge, code_challenge_method="S256")
    assert _exchange(issuer, code=code, code_verifier=verifier).status_code == 200


def test_authorize_rejects_bad_requests(issuer):
    for drop in ("response_type", "client_id", "redirect_uri"):
        params = _authorize_params(login_hint="x@example.test")
        del params[drop]
        r = httpx.get(f"{issuer.base_url}/authorize", params=params, follow_redirects=False)
        assert r.status_code == 400 and drop in r.text
    r = httpx.get(f"{issuer.base_url}/authorize", params=_authorize_params(response_type="token"))
    assert r.status_code == 400
    r = httpx.get(f"{issuer.base_url}/authorize", params=_authorize_params(redirect_uri="/relative"))
    assert r.status_code == 400
    r = httpx.get(f"{issuer.base_url}/authorize", params=_authorize_params(flags="nonsense"))
    assert r.status_code == 400 and "nonsense" in r.text
    r = httpx.get(f"{issuer.base_url}/authorize", params=_authorize_params(code_challenge="c", code_challenge_method="S512"))
    assert r.status_code == 400


def test_form_rejects_empty_or_malformed_email_and_rerenders(issuer):
    params = _authorize_params()
    for email, msg in (("", "Enter an email address."), ("   ", "Enter an email address."), ("no-at-sign", "Enter a valid email address.")):
        r = httpx.post(f"{issuer.base_url}/authorize", data={**params, "email": email}, follow_redirects=False)
        assert r.status_code == 400
        assert msg in r.text and 'id="email"' in r.text
        assert f'value="{params["state"]}"' in r.text  # hidden fields preserved for the retry


def test_cancel_returns_access_denied(issuer):
    params = _authorize_params()
    r = httpx.post(f"{issuer.base_url}/authorize", data={**params, "deny": "1"}, follow_redirects=False)
    assert r.status_code == 302
    back = parse_qs(urlsplit(r.headers["location"]).query)
    assert back == {"error": ["access_denied"], "state": [params["state"]]}


def test_control_and_userinfo_errors(issuer):
    r = httpx.post(f"{issuer.base_url}/_control", json={"flags": {"bogus": True}})
    assert r.status_code == 400 and "bogus" in r.json()["error_description"]
    assert httpx.get(f"{issuer.base_url}/_control").json()["flags"] == []
    assert httpx.get(f"{issuer.base_url}/userinfo").status_code == 401
    assert httpx.get(f"{issuer.base_url}/userinfo", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert httpx.get(f"{issuer.base_url}/nope").status_code == 404


def test_client_id_restriction():
    with run_in_thread(client_id=CLIENT_ID) as srv:
        ok = httpx.get(f"{srv.base_url}/authorize", params=_authorize_params(login_hint="a@example.test"), follow_redirects=False)
        assert ok.status_code == 302
        bad = httpx.get(f"{srv.base_url}/authorize", params=_authorize_params(client_id="other", login_hint="a@example.test"), follow_redirects=False)
        assert bad.status_code == 400
