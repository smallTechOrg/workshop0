"""OIDC client (discovery, PKCE S256 + state + nonce, code exchange, ID-token verification).

spec/architecture.md §Network identity. Works against any standards-compliant issuer —
Google in production, `tests/support/fake_oidc.py` locally. ID tokens are verified against
the issuer's JWKS: RS256 only, `iss`, `aud` = client id, `exp` with 60 s leeway, `nonce`.

Every failure raises `OidcError(code, reason)`: `code` is the redirect code the callback
puts in `/app/signin/?error=<code>`, `reason` is the finer log-only cause.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

SCOPES = "openid email profile"
ID_TOKEN_ALGORITHMS = ["RS256"]
CLOCK_LEEWAY_S = 60
HTTP_TIMEOUT_S = 10.0
DISCOVERY_TTL_S = 3600
JWKS_TTL_S = 3600
JWKS_MIN_REFRESH_S = 30  # unknown-kid refetches are throttled to one per 30 s
GOOGLE_ISSUER = "https://accounts.google.com"

# Test seam: an `httpx.BaseTransport` (e.g. `httpx.MockTransport`) used for every IdP call
# when set. Production leaves it None (real network).
transport: httpx.BaseTransport | None = None


class OidcError(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class ProviderMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


@dataclass(frozen=True)
class FlowSecrets:
    state: str
    nonce: str
    code_verifier: str

    @property
    def code_challenge(self) -> str:
        return pkce_challenge(self.code_verifier)


@dataclass(frozen=True)
class IdTokenClaims:
    issuer: str
    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


_lock = threading.Lock()
_discovery_cache: dict[str, tuple[float, ProviderMetadata]] = {}
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def reset_caches() -> None:
    with _lock:
        _discovery_cache.clear()
        _jwks_cache.clear()


def _client() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT_S, transport=transport, follow_redirects=False)


def normalize_issuer(issuer: str) -> str:
    return issuer.strip().rstrip("/")


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_flow() -> FlowSecrets:
    return FlowSecrets(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        code_verifier=secrets.token_urlsafe(64),  # 86 chars — within RFC 7636's 43..128
    )


def discover(issuer: str) -> ProviderMetadata:
    """`{issuer}/.well-known/openid-configuration`, cached for an hour per issuer."""
    issuer = normalize_issuer(issuer)
    now = time.monotonic()
    with _lock:
        cached = _discovery_cache.get(issuer)
        if cached and now - cached[0] < DISCOVERY_TTL_S:
            return cached[1]
    try:
        with _client() as client:
            response = client.get(f"{issuer}/.well-known/openid-configuration")
        response.raise_for_status()
        document = response.json()
        metadata = ProviderMetadata(
            issuer=normalize_issuer(str(document["issuer"])),
            authorization_endpoint=str(document["authorization_endpoint"]),
            token_endpoint=str(document["token_endpoint"]),
            jwks_uri=str(document["jwks_uri"]),
        )
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise OidcError("idp_error", f"discovery_failed:{type(exc).__name__}") from exc
    if metadata.issuer != issuer:
        raise OidcError("idp_error", "discovery_issuer_mismatch")
    with _lock:
        _discovery_cache[issuer] = (now, metadata)
    return metadata


def authorization_url(
    metadata: ProviderMetadata, *, client_id: str, redirect_uri: str, flow: FlowSecrets
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": flow.state,
        "nonce": flow.nonce,
        "code_challenge": flow.code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    separator = "&" if "?" in metadata.authorization_endpoint else "?"
    return f"{metadata.authorization_endpoint}{separator}{urlencode(params)}"


def exchange_code(
    metadata: ProviderMetadata,
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
) -> str:
    """Authorization-code grant (client_secret_post + PKCE verifier) → the raw ID token."""
    try:
        with _client() as client:
            response = client.post(
                metadata.token_endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code_verifier": code_verifier,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise OidcError("idp_error", f"token_request_failed:{type(exc).__name__}") from exc
    if response.status_code != 200:
        raise OidcError("idp_error", f"token_endpoint_status_{response.status_code}")
    try:
        id_token = response.json().get("id_token")
    except ValueError as exc:
        raise OidcError("idp_error", "token_response_not_json") from exc
    if not isinstance(id_token, str) or not id_token:
        raise OidcError("idp_error", "token_response_missing_id_token")
    return id_token


def _fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    try:
        with _client() as client:
            response = client.get(jwks_uri)
        response.raise_for_status()
        document = response.json()
        if not isinstance(document.get("keys"), list):
            raise ValueError("jwks without keys")
        return document
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise OidcError("idp_error", f"jwks_fetch_failed:{type(exc).__name__}") from exc


def _jwks(jwks_uri: str, *, force: bool) -> dict[str, Any]:
    now = time.monotonic()
    with _lock:
        cached = _jwks_cache.get(jwks_uri)
    if cached is not None:
        age = now - cached[0]
        if age < JWKS_TTL_S and not (force and age >= JWKS_MIN_REFRESH_S):
            return cached[1]
    document = _fetch_jwks(jwks_uri)
    with _lock:
        _jwks_cache[jwks_uri] = (time.monotonic(), document)
    return document


def _pick_key(document: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
    candidates = [
        k
        for k in document["keys"]
        if isinstance(k, dict) and k.get("kty") == "RSA" and k.get("use", "sig") == "sig"
    ]
    if kid is not None:
        candidates = [k for k in candidates if k.get("kid") == kid]
    elif len(candidates) != 1:
        return None  # no kid and an ambiguous key set: refuse rather than guess
    return candidates[0] if candidates else None


def _signing_key(metadata: ProviderMetadata, kid: str | None) -> jwt.PyJWK:
    """Key for `kid` from the (cached) JWKS; an unknown kid triggers one throttled refetch
    so the IdP's key rotation is picked up."""
    jwk = _pick_key(_jwks(metadata.jwks_uri, force=False), kid)
    if jwk is None:
        jwk = _pick_key(_jwks(metadata.jwks_uri, force=True), kid)
    if jwk is None:
        raise OidcError("idp_error", "signing_key_not_found")
    try:
        return jwt.PyJWK(jwk, algorithm="RS256")
    except jwt.PyJWKError as exc:
        raise OidcError("idp_error", "jwks_key_invalid") from exc


def _accepted_issuers(issuer: str) -> list[str]:
    # Google documents both forms for the `iss` claim.
    if issuer == GOOGLE_ISSUER:
        return [GOOGLE_ISSUER, "accounts.google.com"]
    return [issuer]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def verify_id_token(
    id_token: str, *, metadata: ProviderMetadata, client_id: str, nonce: str
) -> IdTokenClaims:
    """Signature (JWKS, RS256), `iss`, `aud`, `exp` (+60 s leeway), `iat`, `nonce`."""
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise OidcError("idp_error", "id_token_malformed") from exc
    if header.get("alg") not in ID_TOKEN_ALGORITHMS:
        raise OidcError("idp_error", "id_token_bad_alg")
    key = _signing_key(metadata, header.get("kid"))
    try:
        claims = jwt.decode(
            id_token,
            key=key.key,
            algorithms=ID_TOKEN_ALGORITHMS,
            audience=client_id,
            issuer=_accepted_issuers(metadata.issuer),
            leeway=CLOCK_LEEWAY_S,
            options={"require": ["iss", "aud", "exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise OidcError("idp_error", "id_token_expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise OidcError("idp_error", "id_token_bad_audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise OidcError("idp_error", "id_token_bad_issuer") from exc
    except jwt.InvalidSignatureError as exc:
        raise OidcError("idp_error", "id_token_bad_signature") from exc
    except jwt.PyJWTError as exc:
        raise OidcError("idp_error", f"id_token_invalid:{type(exc).__name__}") from exc
    # A multi-audience token must name us as the authorized party (OIDC Core §3.1.3.7).
    aud = claims.get("aud")
    if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != client_id:
        raise OidcError("idp_error", "id_token_bad_azp")
    token_nonce = claims.get("nonce")
    if not isinstance(token_nonce, str) or not secrets.compare_digest(
        token_nonce.encode("utf-8"), nonce.encode("utf-8")
    ):
        raise OidcError("idp_error", "nonce_mismatch")
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise OidcError("idp_error", "id_token_missing_email")
    if not _as_bool(claims.get("email_verified")):
        raise OidcError("email_unverified", "email_unverified")
    name = claims.get("name")
    picture = claims.get("picture")
    return IdTokenClaims(
        issuer=metadata.issuer,
        subject=str(claims["sub"]),
        email=email.strip().lower(),
        email_verified=True,
        name=name.strip() if isinstance(name, str) and name.strip() else None,
        picture=picture
        if isinstance(picture, str) and picture.startswith(("https://", "http://")) and len(picture) <= 500
        else None,
    )
