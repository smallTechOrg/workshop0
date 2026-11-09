"""A local OpenID Connect test issuer, built only so Workshop0 can run a real sign-in in tests.

It speaks the real authorization-code protocol that `src/workshop0/auth/oidc.py` uses
against Google: discovery, an authorize page, PKCE, a token endpoint, RS256 ID tokens and
a JWKS. Because nothing is faked on the app side, the auth tests (S1) and the Playwright
journeys (S13/S14) exercise the same code path production uses.

Run it as a process (this is what the Phase-11 gate does)::

    uv run python tests/support/fake_oidc.py --port 8099
    # app side:  WORKSHOP0_OIDC_ISSUER=http://localhost:8099

or start it inside pytest::

    from tests.support.fake_oidc import run_in_thread
    issuer = run_in_thread()            # port 0 = pick a free port
    issuer.base_url                     # "http://localhost:<port>", also the `iss` claim
    issuer.stop()

Endpoints
---------
``GET  /.well-known/openid-configuration``  discovery document; ``issuer`` is
                                             ``http://localhost:<port>`` unless ``--issuer``.
``GET  /authorize``    HTML sign-in page. Needs ``response_type=code``, ``client_id``,
                       ``redirect_uri``; carries ``state``, ``nonce``, ``scope``,
                       ``code_challenge`` / ``code_challenge_method`` (S256 or plain).
                       The page has one text field (``id``/``name`` = ``email``, label
                       "Email") and a submit button "Sign in". Submitting approves
                       automatically and 302s to ``redirect_uri?code=…&state=…``.
                       If ``login_hint`` or ``email`` is in the query, the form is skipped
                       and the redirect happens immediately.
``POST /authorize``    The form posts here (same parameters plus ``email``).
``POST /token``        ``grant_type=authorization_code``, ``code``, ``redirect_uri``,
                       ``client_id`` (form field or HTTP Basic), ``client_secret`` (accepted
                       as-is), ``code_verifier`` (checked when a challenge was sent).
                       Codes are single-use and valid for 5 minutes. Returns
                       ``{access_token, token_type, expires_in, scope, id_token}``.
``GET  /jwks``         The RS256 public key (``kid`` = ``fake-oidc-key-1``). The second
                       ("rogue") key is never published.
``GET  /userinfo``     Claims for ``Authorization: Bearer <access_token>``.
``GET  /avatar/<sub>.svg``  The image the ``picture`` claim points at.
``GET/POST /_control`` Read / set the issuer-wide negative-case flags (see below).
``POST /_control/reset``  Clear them.

ID-token claims: ``iss``, ``aud`` (= client_id), ``sub`` (stable per lower-cased email:
``fake-`` + 24 hex chars of its SHA-256), ``email``, ``email_verified``, ``nonce`` (echoed
from the authorize request; omitted if none was sent), ``iat``, ``exp`` (iat + 3600),
``name`` (from the email local part), ``picture``.

Negative cases
--------------
Each flag makes the issuer produce one kind of token the app must refuse:

=================  ===================  =================================================
flag               magic email tag      effect on the ID token
=================  ===================  =================================================
``unverified``     ``unverified``       ``email_verified: false``
``wrong_aud``      ``wrongaud``         ``aud: "wrong-client-id"``
``expired``        ``expired``          ``iat`` = now − 2 h, ``exp`` = now − 1 h (beyond any leeway)
``bad_signature``  ``badsig``           signed by a second RSA key that is NOT in the JWKS,
                                        header ``kid`` = the published kid, so verification
                                        fails on the signature itself
``unknown_kid``    ``unknownkid``       signed by the second key with its own ``kid``
                                        (``fake-oidc-rogue-key``), absent from the JWKS
``wrong_iss``      ``wrongiss``         ``iss: "http://wrong-issuer.example"``
``bad_nonce``      ``badnonce``         ``nonce`` replaced by a different value
=================  ===================  =================================================

Three ways to set them, from most to least local; the token gets the union of all three:

1. **Magic email (per sign-in — preferred, safe with parallel tests).** Any ``+``-separated
   segment of the email's local part that equals a tag turns that flag on:
   ``unverified+t1@example.test``, ``alice+expired@example.test``,
   ``badsig+wrongaud+x@example.test``. The email claim is the address exactly as typed.
2. **Authorize page checkboxes** (manual testing): one per flag, unchecked by default; or
   ``flags=unverified,expired`` in the authorize query (comma-separated flag names).
3. **Issuer-wide.** CLI: ``--unverified --wrong-aud --expired --bad-signature
   --unknown-kid --wrong-iss --bad-nonce``. At runtime: ``POST /_control`` with JSON
   ``{"flags": {"expired": true}}`` (merged into the current set; ``"replace": true`` replaces
   it), ``GET /_control`` to read, ``POST /_control/reset`` to clear. In-process:
   ``issuer.set_flags(expired=True)`` / ``issuer.reset()``. Issuer-wide flags affect every
   concurrent test, so prefer magic emails.

Flags are captured when the authorization code is issued, so a code minted while a flag
was on keeps it even if the flag is cleared before the exchange.

Also: ``issuer.mint_id_token(email=…, aud=…, nonce=…, flags=…)`` signs a token directly,
and ``authorize_redirect(authorize_url, email)`` follows the authorize step with httpx and
returns the ``redirect_uri?code=…&state=…`` URL the browser would land on.

Only the stdlib, ``pyjwt[crypto]`` and ``cryptography`` are used, so the script runs
with no import of the app.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import secrets
import sys
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

KID = "fake-oidc-key-1"
ROGUE_KID = "fake-oidc-rogue-key"
WRONG_AUD = "wrong-client-id"
WRONG_ISS = "http://wrong-issuer.example"
CODE_TTL_S = 300
TOKEN_TTL_S = 3600

# flag name -> magic email tag
FLAGS: dict[str, str] = {
    "unverified": "unverified",
    "wrong_aud": "wrongaud",
    "expired": "expired",
    "bad_signature": "badsig",
    "unknown_kid": "unknownkid",
    "wrong_iss": "wrongiss",
    "bad_nonce": "badnonce",
}
_TAG_TO_FLAG = {tag: name for name, tag in FLAGS.items()}

FLAG_LABELS: dict[str, str] = {
    "unverified": "email_verified = false",
    "wrong_aud": "wrong aud",
    "expired": "expired token",
    "bad_signature": "bad signature (second key, published kid)",
    "unknown_kid": "unknown kid (second key)",
    "wrong_iss": "wrong iss",
    "bad_nonce": "wrong nonce",
}


def flags_from_email(email: str) -> set[str]:
    """Flags encoded as ``+``-separated tags in the email's local part."""
    local = email.split("@", 1)[0].lower()
    return {_TAG_TO_FLAG[seg] for seg in local.split("+") if seg in _TAG_TO_FLAG}


def parse_flag_list(value: str | None) -> set[str]:
    """``"unverified, expired"`` -> ``{"unverified", "expired"}``; unknown names raise ValueError."""
    if not value:
        return set()
    names = {v.strip() for v in value.split(",") if v.strip()}
    unknown = names - FLAGS.keys()
    if unknown:
        raise ValueError(f"unknown flag(s): {', '.join(sorted(unknown))}")
    return names


def subject_for(email: str) -> str:
    return "fake-" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:24]


def display_name_for(email: str) -> str:
    local = email.split("@", 1)[0]
    words = [w for w in local.replace(".", " ").replace("_", " ").replace("-", " ").replace("+", " ").split() if w]
    return " ".join(w.capitalize() for w in words) or email


def pkce_s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


@dataclass
class _Grant:
    client_id: str
    redirect_uri: str
    email: str
    nonce: str | None
    scope: str
    flags: frozenset[str]
    code_challenge: str | None
    code_challenge_method: str
    expires_at: float


@dataclass
class IssuerState:
    """Keys, outstanding codes and access tokens, and the issuer-wide flags."""

    issuer: str
    base_url: str
    flags: set[str] = field(default_factory=set)
    client_id: str | None = None  # when set, other client ids are refused
    lock: threading.Lock = field(default_factory=threading.Lock)
    codes: dict[str, _Grant] = field(default_factory=dict)
    access_tokens: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # --- documents -------------------------------------------------------------
    def discovery(self) -> dict[str, Any]:
        b = self.base_url
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{b}/authorize",
            "token_endpoint": f"{b}/token",
            "jwks_uri": f"{b}/jwks",
            "userinfo_endpoint": f"{b}/userinfo",
            "response_types_supported": ["code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "email", "profile"],
            "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
            "claims_supported": ["iss", "aud", "sub", "email", "email_verified", "nonce", "iat", "exp", "name", "picture"],
            "code_challenge_methods_supported": ["S256", "plain"],
            "grant_types_supported": ["authorization_code"],
        }

    def jwks(self) -> dict[str, Any]:
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
        return {"keys": [jwk]}

    # --- tokens ----------------------------------------------------------------
    def claims_for(self, email: str, aud: str, nonce: str | None, flags: set[str] | frozenset[str]) -> dict[str, Any]:
        now = int(time.time())
        iat = now - 7200 if "expired" in flags else now
        exp = now - 3600 if "expired" in flags else now + TOKEN_TTL_S
        sub = subject_for(email)
        claims: dict[str, Any] = {
            "iss": WRONG_ISS if "wrong_iss" in flags else self.issuer,
            "aud": WRONG_AUD if "wrong_aud" in flags else aud,
            "sub": sub,
            "email": email,
            "email_verified": "unverified" not in flags,
            "iat": iat,
            "exp": exp,
            "name": display_name_for(email),
            "picture": f"{self.base_url}/avatar/{sub}.svg",
        }
        if nonce is not None:
            claims["nonce"] = ("wrong-" + secrets.token_urlsafe(8)) if "bad_nonce" in flags else nonce
        return claims

    def mint_id_token(
        self,
        *,
        email: str,
        aud: str,
        nonce: str | None = None,
        flags: set[str] | frozenset[str] | None = None,
    ) -> str:
        """Sign an ID token now. ``flags`` (names from FLAGS) are applied on top of the
        email's magic tags and the issuer-wide flags."""
        active = set(flags or ()) | flags_from_email(email) | self.current_flags()
        claims = self.claims_for(email, aud, nonce, active)
        if "unknown_kid" in active:
            return jwt.encode(claims, self.rogue_key, algorithm="RS256", headers={"kid": ROGUE_KID})
        if "bad_signature" in active:
            return jwt.encode(claims, self.rogue_key, algorithm="RS256", headers={"kid": KID})
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": KID})

    # --- flags -----------------------------------------------------------------
    def current_flags(self) -> set[str]:
        with self.lock:
            return set(self.flags)

    def update_flags(self, values: dict[str, bool], replace: bool = False) -> set[str]:
        unknown = set(values) - FLAGS.keys()
        if unknown:
            raise ValueError(f"unknown flag(s): {', '.join(sorted(unknown))}")
        with self.lock:
            if replace:
                self.flags = set()
            for name, on in values.items():
                (self.flags.add if on else self.flags.discard)(name)
            return set(self.flags)


class _Handler(BaseHTTPRequestHandler):
    server_version = "fake-oidc/1"
    state: IssuerState  # set on the subclass built per server
    quiet: bool = False

    # --- plumbing --------------------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - stdlib signature
        if not self.quiet:
            sys.stderr.write(f"fake-oidc {self.address_string()} {fmt % args}\n")

    def _send(self, status: int, body: bytes, content_type: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any, extra: dict[str, str] | None = None) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json", extra)

    def _oauth_error(self, status: int, error: str, description: str) -> None:
        self._json(status, {"error": error, "error_description": description})

    def _html(self, status: int, markup: str) -> None:
        self._send(status, markup.encode(), "text/html; charset=utf-8")

    def _redirect(self, location: str) -> None:
        self._send(302, b"", "text/plain", {"Location": location})

    def _query(self) -> dict[str, str]:
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query, keep_blank_values=True).items()}

    def _form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode() if length else ""
        return parse_qs(raw, keep_blank_values=True)

    def _json_body(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw) if raw.strip() else {}

    # --- routing ---------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        path = urlsplit(self.path).path
        if path == "/.well-known/openid-configuration":
            return self._json(200, self.state.discovery())
        if path == "/jwks":
            return self._json(200, self.state.jwks())
        if path == "/authorize":
            params = self._query()
            return self._authorize(params, params.get("login_hint") or params.get("email"), set())
        if path == "/userinfo":
            return self._userinfo()
        if path == "/_control":
            return self._json(200, {"flags": sorted(self.state.current_flags()), "known_flags": FLAGS})
        if path.startswith("/avatar/"):
            return self._avatar(path)
        if path in ("/", "/health"):
            return self._json(200, {"status": "ok", "issuer": self.state.issuer})
        return self._json(404, {"error": "not_found"})

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        path = urlsplit(self.path).path
        if path == "/authorize":
            form = self._form()
            params = {k: v[0] for k, v in form.items()}
            checked = {name for name in form.get("flag", []) if name in FLAGS}
            if "deny" in params:
                return self._deny(params)
            return self._authorize(params, params.get("email", ""), checked, from_form=True)
        if path == "/token":
            return self._token()
        if path == "/_control":
            try:
                body = self._json_body()
                flags = self.state.update_flags(dict(body.get("flags", {})), replace=bool(body.get("replace")))
            except (ValueError, TypeError, AttributeError) as exc:
                return self._json(400, {"error": "invalid_request", "error_description": str(exc)})
            return self._json(200, {"flags": sorted(flags)})
        if path == "/_control/reset":
            return self._json(200, {"flags": sorted(self.state.update_flags({}, replace=True))})
        return self._json(404, {"error": "not_found"})

    # --- authorize -------------------------------------------------------------
    def _authorize(self, params: dict[str, str], email: str | None, checked: set[str], from_form: bool = False) -> None:
        missing = [p for p in ("response_type", "client_id", "redirect_uri") if not params.get(p)]
        if missing:
            return self._html(400, _error_page(f"Missing required parameter(s): {', '.join(missing)}."))
        if params["response_type"] != "code":
            return self._html(400, _error_page("Only response_type=code is supported."))
        if self.state.client_id and params["client_id"] != self.state.client_id:
            return self._html(400, _error_page("Unknown client_id."))
        redirect = urlsplit(params["redirect_uri"])
        if redirect.scheme not in ("http", "https") or not redirect.netloc:
            return self._html(400, _error_page("redirect_uri must be an absolute http(s) URL."))
        method = params.get("code_challenge_method") or ("plain" if params.get("code_challenge") else "")
        if params.get("code_challenge") and method not in ("S256", "plain"):
            return self._html(400, _error_page("code_challenge_method must be S256 or plain."))
        try:
            query_flags = parse_flag_list(params.get("flags"))
        except ValueError as exc:
            return self._html(400, _error_page(str(exc)))

        email = (email or "").strip()
        if not email:
            error = "Enter an email address." if from_form else None
            return self._html(400 if from_form else 200, _signin_page(params, error))
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            return self._html(400, _signin_page(params, "Enter a valid email address.", email))

        flags = frozenset(query_flags | checked | flags_from_email(email) | self.state.current_flags())
        code = secrets.token_urlsafe(24)
        grant = _Grant(
            client_id=params["client_id"],
            redirect_uri=params["redirect_uri"],
            email=email,
            nonce=params.get("nonce") or None,
            scope=params.get("scope") or "openid email profile",
            flags=flags,
            code_challenge=params.get("code_challenge") or None,
            code_challenge_method=method or "plain",
            expires_at=time.time() + CODE_TTL_S,
        )
        with self.state.lock:
            self.state.codes[code] = grant
        out = {"code": code}
        if params.get("state"):
            out["state"] = params["state"]
        self._redirect(_add_query(params["redirect_uri"], out))

    def _deny(self, params: dict[str, str]) -> None:
        if not params.get("redirect_uri"):
            return self._html(400, _error_page("Missing redirect_uri."))
        out = {"error": "access_denied"}
        if params.get("state"):
            out["state"] = params["state"]
        self._redirect(_add_query(params["redirect_uri"], out))

    # --- token -----------------------------------------------------------------
    def _token(self) -> None:
        form = {k: v[0] for k, v in self._form().items()}
        client_id = form.get("client_id")
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(auth[6:]).decode()
                client_id = client_id or decoded.split(":", 1)[0]
            except (ValueError, UnicodeDecodeError):
                return self._oauth_error(401, "invalid_client", "Malformed Basic credentials.")
        if form.get("grant_type") != "authorization_code":
            return self._oauth_error(400, "unsupported_grant_type", "Only authorization_code is supported.")
        code = form.get("code", "")
        if not code:
            return self._oauth_error(400, "invalid_request", "Missing code.")
        if not client_id:
            return self._oauth_error(401, "invalid_client", "Missing client_id.")
        with self.state.lock:
            grant = self.state.codes.pop(code, None)  # single use, even when the exchange fails
        if grant is None or grant.expires_at < time.time():
            return self._oauth_error(400, "invalid_grant", "Unknown, used or expired code.")
        if client_id != grant.client_id:
            return self._oauth_error(400, "invalid_grant", "client_id does not match the code.")
        if form.get("redirect_uri") != grant.redirect_uri:
            return self._oauth_error(400, "invalid_grant", "redirect_uri does not match the authorize request.")
        if grant.code_challenge:
            verifier = form.get("code_verifier", "")
            if not verifier:
                return self._oauth_error(400, "invalid_grant", "Missing code_verifier.")
            computed = pkce_s256(verifier) if grant.code_challenge_method == "S256" else verifier
            if not secrets.compare_digest(computed, grant.code_challenge):
                return self._oauth_error(400, "invalid_grant", "PKCE verification failed.")

        id_token = self.state.mint_id_token(email=grant.email, aud=grant.client_id, nonce=grant.nonce, flags=grant.flags)
        access_token = secrets.token_urlsafe(24)
        claims = self.state.claims_for(grant.email, grant.client_id, grant.nonce, grant.flags)
        with self.state.lock:
            self.state.access_tokens[access_token] = {
                k: claims[k] for k in ("sub", "email", "email_verified", "name", "picture")
            }
        self._json(
            200,
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": TOKEN_TTL_S,
                "scope": grant.scope,
                "id_token": id_token,
            },
        )

    def _userinfo(self) -> None:
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        with self.state.lock:
            info = self.state.access_tokens.get(token)
        if info is None:
            return self._json(401, {"error": "invalid_token"}, {"WWW-Authenticate": 'Bearer error="invalid_token"'})
        self._json(200, info)

    def _avatar(self, path: str) -> None:
        sub = path.rsplit("/", 1)[-1].removesuffix(".svg")
        hue = int(hashlib.sha256(sub.encode()).hexdigest()[:4], 16) % 360
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">'
            f'<rect width="96" height="96" rx="48" fill="hsl({hue},55%,55%)"/></svg>'
        )
        self._send(200, svg.encode(), "image/svg+xml")


def _add_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = parts.query + ("&" if parts.query else "") + urlencode(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


_PAGE_STYLE = (
    "body{font-family:system-ui,sans-serif;background:#f5f5f4;display:flex;justify-content:center;"
    "padding-top:10vh;margin:0}main{background:#fff;border-radius:12px;padding:32px;width:360px;"
    "box-shadow:0 1px 4px rgba(0,0,0,.1)}h1{font-size:20px;margin:0 0 4px}p{color:#57534e;font-size:14px}"
    "label{display:block;font-size:14px;margin:16px 0 4px}input[type=email]{width:100%;box-sizing:border-box;"
    "padding:8px;font-size:16px;border:1px solid #a8a29e;border-radius:6px}button{margin-top:16px;padding:8px 16px;"
    "font-size:16px;border-radius:6px;border:0;background:#1c1917;color:#fff;cursor:pointer}"
    "button.secondary{background:#e7e5e4;color:#1c1917;margin-left:8px}.error{color:#b91c1c}"
    "details{margin-top:20px;font-size:13px}details label{display:inline;margin:0}"
)


def _signin_page(params: dict[str, str], error: str | None, email: str = "") -> str:
    keep = ("response_type", "client_id", "redirect_uri", "scope", "state", "nonce", "code_challenge", "code_challenge_method", "flags")
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{html.escape(params[k])}">' for k in keep if params.get(k)
    )
    boxes = "".join(
        f'<div><input type="checkbox" name="flag" value="{name}" id="flag-{name}"> '
        f'<label for="flag-{name}">{html.escape(label)}</label></div>'
        for name, label in FLAG_LABELS.items()
    )
    err = f'<p class="error" role="alert" data-testid="fake-oidc-error">{html.escape(error)}</p>' if error else ""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Fake OIDC sign-in</title>"
        f"<style>{_PAGE_STYLE}</style></head><body><main>"
        "<h1>Test identity provider</h1>"
        f"<p>Signing in to <strong>{html.escape(params.get('client_id', ''))}</strong>. "
        "Any email is accepted; this issuer exists only for local testing.</p>"
        f'<form method="post" action="/authorize">{hidden}'
        '<label for="email">Email</label>'
        f'<input type="email" id="email" name="email" data-testid="fake-oidc-email" autocomplete="email" '
        f'value="{html.escape(email)}" autofocus>'
        f"{err}"
        '<button type="submit" id="signin" data-testid="fake-oidc-signin">Sign in</button>'
        '<button type="submit" name="deny" value="1" class="secondary" formnovalidate>Cancel</button>'
        f"<details><summary>Negative-case flags</summary>{boxes}</details>"
        "</form></main></body></html>"
    )


def _error_page(message: str) -> str:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Fake OIDC error</title>"
        f"<style>{_PAGE_STYLE}</style></head><body><main><h1>Sign-in request rejected</h1>"
        f'<p class="error" role="alert">{html.escape(message)}</p></main></body></html>'
    )


class FakeOIDC:
    """A running issuer. ``base_url`` is where it listens; ``issuer`` is the ``iss`` claim."""

    def __init__(
        self,
        port: int = 0,
        *,
        host: str = "127.0.0.1",
        issuer: str | None = None,
        flags: set[str] | None = None,
        client_id: str | None = None,
        quiet: bool = True,
    ) -> None:
        self._httpd = ThreadingHTTPServer((host, port), _Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self.base_url = f"http://localhost:{self.port}"
        self.state = IssuerState(issuer=(issuer or self.base_url).rstrip("/"), base_url=self.base_url, client_id=client_id)
        self.state.update_flags({name: True for name in (flags or set())})
        self._httpd.RequestHandlerClass = type("BoundHandler", (_Handler,), {"state": self.state, "quiet": quiet})
        self._thread: threading.Thread | None = None

    @property
    def issuer(self) -> str:
        return self.state.issuer

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def start(self) -> FakeOIDC:
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="fake-oidc", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def set_flags(self, replace: bool = False, **values: bool) -> set[str]:
        return self.state.update_flags(values, replace=replace)

    def reset(self) -> None:
        self.state.update_flags({}, replace=True)

    def mint_id_token(self, **kwargs: Any) -> str:
        return self.state.mint_id_token(**kwargs)

    def jwks(self) -> dict[str, Any]:
        return self.state.jwks()

    def __enter__(self) -> FakeOIDC:
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def run_in_thread(port: int = 0, **kwargs: Any) -> FakeOIDC:
    """Start an issuer on a daemon thread and return it (call ``.stop()``, or use ``with``).

    ``port=0`` picks a free port. Keyword arguments go to :class:`FakeOIDC`
    (``issuer``, ``flags``, ``client_id``, ``quiet``, ``host``)."""
    return FakeOIDC(port, **kwargs).start()


def authorize_redirect(authorize_url: str, email: str, *, timeout: float = 10.0) -> str:
    """Perform the browser's authorize step for ``email`` and return the redirect target
    (``redirect_uri?code=…&state=…``). ``authorize_url`` is the issuer URL the app sent the
    browser to, e.g. the ``Location`` of ``/api/auth/google/start``."""
    import httpx  # imported lazily: the CLI must not need it

    url = _add_query(authorize_url, {"login_hint": email})
    resp = httpx.get(url, follow_redirects=False, timeout=timeout)
    if resp.status_code != 302:
        raise RuntimeError(f"authorize did not redirect (HTTP {resp.status_code}): {resp.text[:200]}")
    return resp.headers["location"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local OpenID Connect issuer for Workshop0 tests.")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--issuer", default=None, help="iss / discovery issuer (default http://localhost:<port>)")
    parser.add_argument("--client-id", default=None, help="if set, refuse any other client_id")
    parser.add_argument("--quiet", action="store_true", help="no request log on stderr")
    for name in FLAGS:
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, action="store_true", help=f"every token: {FLAG_LABELS[name]}")
    args = parser.parse_args(argv)
    flags = {name for name in FLAGS if getattr(args, name)}
    try:
        issuer = FakeOIDC(args.port, host=args.host, issuer=args.issuer, flags=flags, client_id=args.client_id, quiet=args.quiet)
    except OSError as exc:
        print(f"fake-oidc: cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    print(
        f"fake-oidc: issuer {issuer.issuer} listening on {args.host}:{issuer.port}"
        + (f" flags={','.join(sorted(flags))}" if flags else ""),
        file=sys.stderr,
        flush=True,
    )
    try:
        issuer.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        issuer._httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
