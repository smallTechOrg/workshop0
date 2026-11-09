"""`/api/auth/*` — sign-in config, Google OIDC start/callback, me, sign-out (spec/api.md §Phase 11).

Flow (spec/architecture.md §Network identity):

1. `GET /api/auth/google/start?next&invite` — rate-limited 20/min/IP; guards `next` (open
   redirect); stores state / nonce / PKCE verifier / next / invite in the signed, HttpOnly,
   10-minute `workshop0_oidc` cookie; 302 to the IdP's authorization endpoint.
2. `GET /api/auth/google/callback?code&state` — verifies the state cookie, exchanges the code
   (client secret + PKCE), verifies the ID token (oidc.py), checks the invite with the shared
   `services/invites.check_invite` (Phase 11d ordering), upserts the `app_user`, creates a session, sets
   `workshop0_session`, 303 → `next`. Any failure → 303 `/app/signin/?error=<code>` and
   nothing is written (no user, no session, no invite change).

The endpoints are sync `def`s: the IdP calls are blocking httpx calls and run in the
threadpool.
"""

from __future__ import annotations

import re
import secrets
from urllib.parse import urlencode, urlsplit

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, ok, request_base_url, utcnow
from src.workshop0.auth import oidc, sessions
from src.workshop0.auth.deps import check_csrf, is_admin_email
from src.workshop0.auth.startup import signin_enabled
from src.workshop0.config.settings import Settings, get_settings
from src.workshop0.db.models import AppUser, NetworkInvite, TrainerProfile
from src.workshop0.db.session import get_session
from src.workshop0.services import invites, ratelimit
from src.workshop0.services.workshops import mask_email

log = structlog.get_logger("workshop0")

router = APIRouter(prefix="/api/auth")

OIDC_COOKIE = "workshop0_oidc"
OIDC_COOKIE_PATH = "/api/auth/google"
OIDC_COOKIE_MAX_AGE_S = 600  # 10 minutes
_OIDC_SALT = "workshop0.oidc-state.v1"

DEFAULT_NEXT = "/app/network/"
SIGNIN_PAGE = "/app/signin/"
CALLBACK_PATH = "/api/auth/google/callback"
NEXT_MAX = 500

START_RATE_LIMIT = 20
START_RATE_WINDOW_S = 60

DISPLAY_NAME_MAX = 120
_INVITE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# --------------------------------------------------------------------------- helpers


def safe_next(value: str | None) -> str:
    """Open-redirect guard: a same-origin path under `/app/`, else `/app/network/`."""
    if not value or len(value) > NEXT_MAX:
        return DEFAULT_NEXT
    if not value.startswith("/app/") or "\\" in value or value.startswith("//"):
        return DEFAULT_NEXT
    if any(ord(ch) < 0x21 or ord(ch) == 0x7F for ch in value):  # whitespace / control chars
        return DEFAULT_NEXT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_NEXT
    return value


def clean_invite_token(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value if _INVITE_TOKEN_RE.match(value) else None


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.workshop0_session_secret.strip(), salt=_OIDC_SALT)


def _is_https(request: Request) -> bool:
    return request_base_url(request).lower().startswith("https://")


def _redirect_uri(request: Request) -> str:
    return f"{request_base_url(request)}{CALLBACK_PATH}"


def _clear_oidc_cookie(response, secure: bool) -> None:
    response.delete_cookie(
        OIDC_COOKIE, path=OIDC_COOKIE_PATH, httponly=True, samesite="lax", secure=secure
    )


def _error_redirect(
    request: Request, code: str, *, next_path: str | None = None, extra: dict | None = None
) -> RedirectResponse:
    """303 → `/app/signin/?error=<code>[&<extra>]&next=<next>` (api.md §Phase 11 callback)."""
    params = {"error": code, **(extra or {}), "next": next_path or DEFAULT_NEXT}
    response = RedirectResponse(url=f"{SIGNIN_PAGE}?{urlencode(params)}", status_code=303)
    _clear_oidc_cookie(response, _is_https(request))
    return response


def _display_name(claims: oidc.IdTokenClaims) -> str:
    name = claims.name or claims.email.split("@", 1)[0] or claims.email
    return name[:DISPLAY_NAME_MAX]


def _find_user(session: Session, claims: oidc.IdTokenClaims) -> AppUser | None:
    user = session.scalar(
        select(AppUser).where(
            AppUser.oidc_issuer == claims.issuer, AppUser.oidc_subject == claims.subject
        )
    )
    if user is not None:
        return user
    # An invite-created placeholder (or a row linked to another issuer) with the same
    # IdP-verified email is the same person: claim it.
    return session.scalar(select(AppUser).where(AppUser.email == claims.email))


def _upsert_user(session: Session, user: AppUser | None, claims: oidc.IdTokenClaims) -> AppUser:
    now = utcnow()
    if user is None:
        user = AppUser(
            email=claims.email,
            email_verified=True,
            display_name=_display_name(claims),
            avatar_url=claims.picture,
            oidc_issuer=claims.issuer,
            oidc_subject=claims.subject,
            created_at=now,
            last_login_at=now,
        )
        session.add(user)
        session.flush()
        log.info("auth.user_created", user_id=user.id)
        return user
    if (user.oidc_issuer, user.oidc_subject) != (claims.issuer, claims.subject):
        log.info(
            "auth.account_linked",
            user_id=user.id,
            placeholder=user.oidc_issuer is None,
        )
        user.oidc_issuer = claims.issuer
        user.oidc_subject = claims.subject
    if user.email != claims.email:
        taken = session.scalar(
            select(AppUser.id).where(AppUser.email == claims.email, AppUser.id != user.id)
        )
        if taken is None:
            user.email = claims.email
    user.email_verified = True
    user.display_name = _display_name(claims)
    user.avatar_url = claims.picture
    user.last_login_at = now
    session.flush()
    return user


def _serialize_user(session: Session, user: AppUser) -> dict:
    has_profile = bool(
        session.scalar(select(exists().where(TrainerProfile.user_id == user.id)))
    )
    invite_accepted = bool(
        session.scalar(
            select(
                exists().where(
                    NetworkInvite.accepted_user_id == user.id,
                    NetworkInvite.accepted_at.is_not(None),
                )
            )
        )
    )
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "is_admin": is_admin_email(user.email, user.email_verified),
        "has_profile": has_profile,
        "invite_accepted": invite_accepted,
    }


# --------------------------------------------------------------------------- endpoints


@router.get("/config")
def auth_config():
    return ok({"google_enabled": signin_enabled(get_settings())})


@router.get("/google/start")
def google_start(
    request: Request,
    next: str | None = None,  # noqa: A002 — the documented query parameter name
    invite: str | None = None,
    session: Session = Depends(get_session),
):
    settings = get_settings()
    if not signin_enabled(settings):
        raise api_error(
            "signin_not_configured",
            "Sign-in isn't set up on this server — the operator hasn't added Google credentials.",
            503,
        )
    client_ip = request.client.host if request.client else "unknown"
    ratelimit.enforce(
        session, f"oidc_start:{client_ip}"[:120], START_RATE_LIMIT, START_RATE_WINDOW_S
    )
    next_path = safe_next(next)
    invite_token = clean_invite_token(invite)
    try:
        metadata = oidc.discover(settings.workshop0_oidc_issuer)
    except oidc.OidcError as exc:
        log.warning("auth.signin_failed", stage="start", code=exc.code, reason=exc.reason)
        return _error_redirect(request, exc.code, next_path=next_path)

    flow = oidc.new_flow()
    url = oidc.authorization_url(
        metadata,
        client_id=settings.workshop0_google_client_id.strip(),
        redirect_uri=_redirect_uri(request),
        flow=flow,
    )
    payload = {
        "s": flow.state,
        "n": flow.nonce,
        "v": flow.code_verifier,
        "next": next_path,
        "invite": invite_token,
    }
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(
        OIDC_COOKIE,
        _serializer(settings).dumps(payload),
        max_age=OIDC_COOKIE_MAX_AGE_S,
        path=OIDC_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )
    log.info("auth.signin_started", has_invite=invite_token is not None)
    return response


def _load_flow(request: Request, settings: Settings, state: str | None) -> dict:
    raw = request.cookies.get(OIDC_COOKIE)
    if not raw or not state:
        raise oidc.OidcError("state_mismatch", "state_cookie_missing" if not raw else "state_missing")
    try:
        payload = _serializer(settings).loads(raw, max_age=OIDC_COOKIE_MAX_AGE_S)
    except SignatureExpired as exc:
        raise oidc.OidcError("state_mismatch", "state_cookie_expired") from exc
    except BadSignature as exc:
        raise oidc.OidcError("state_mismatch", "state_cookie_bad_signature") from exc
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(k), str) and payload.get(k) for k in ("s", "n", "v")
    ):
        raise oidc.OidcError("state_mismatch", "state_cookie_malformed")
    if not secrets.compare_digest(payload["s"].encode("utf-8"), state.encode("utf-8")):
        raise oidc.OidcError("state_mismatch", "state_value_mismatch")
    return payload


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
):
    settings = get_settings()
    if not signin_enabled(settings):
        return _error_redirect(request, "signin_not_configured")

    next_path: str | None = None
    invite_token: str | None = None
    try:
        flow = _load_flow(request, settings, state)
        next_path = safe_next(flow.get("next") if isinstance(flow.get("next"), str) else None)
        invite_token = clean_invite_token(
            flow.get("invite") if isinstance(flow.get("invite"), str) else None
        )
        if error:
            raise oidc.OidcError("idp_error", f"idp_returned_{error[:40]}")
        if not code:
            raise oidc.OidcError("idp_error", "code_missing")
        client_id = settings.workshop0_google_client_id.strip()
        metadata = oidc.discover(settings.workshop0_oidc_issuer)
        id_token = oidc.exchange_code(
            metadata,
            code=code,
            client_id=client_id,
            client_secret=settings.workshop0_google_client_secret.strip(),
            redirect_uri=_redirect_uri(request),
            code_verifier=flow["v"],
        )
        claims = oidc.verify_id_token(
            id_token, metadata=metadata, client_id=client_id, nonce=flow["n"]
        )
    except oidc.OidcError as exc:
        log.warning("auth.signin_failed", stage="callback", code=exc.code, reason=exc.reason)
        return _error_redirect(request, exc.code, next_path=next_path)

    existing = _find_user(session, claims)
    try:
        match = invites.check_invite(
            session, invite_token, claims.email, existing.id if existing else None
        )
    except invites.InviteRefused as exc:
        log.warning("auth.signin_failed", stage="invite", code=exc.code, reason=exc.code)
        extra = (
            {"invite": invite_token, **exc.extra} if exc.code == "invite_email_mismatch" else None
        )
        return _error_redirect(request, exc.code, next_path=next_path, extra=extra)

    user = _upsert_user(session, existing, claims)
    invite = match.invite if match is not None else None
    profile_verified = False
    if match is not None:
        profile_verified = invites.accept_invite(session, match, user)
        log.info(
            "auth.invite_accepted",
            invite_id=invite.id,
            user_id=user.id,
            profile_verified=profile_verified,
            email=mask_email(user.email),
        )
    token = sessions.create_session(session, user.id, user_agent=request.headers.get("user-agent"))
    session.commit()

    secure = _is_https(request)
    response = RedirectResponse(url=next_path or DEFAULT_NEXT, status_code=303)
    response.set_cookie(
        sessions.SESSION_COOKIE,
        token,
        max_age=sessions.SESSION_MAX_AGE_S,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )
    _clear_oidc_cookie(response, secure)
    log.info(
        "auth.signin",
        user_id=user.id,
        is_admin=is_admin_email(user.email, user.email_verified),
        invite_accepted=invite is not None,
    )
    return response


@router.get("/me")
def auth_me(request: Request, session: Session = Depends(get_session)):
    """Never 401: `{"user": null}` when signed out."""
    user = sessions.resolve(session, request.cookies.get(sessions.SESSION_COOKIE))
    return ok({"user": _serialize_user(session, user) if user is not None else None})


@router.post("/signout")
def auth_signout(request: Request, session: Session = Depends(get_session)):
    """Revokes this browser's session and clears the cookie; idempotent."""
    check_csrf(request)
    revoked = sessions.revoke(session, request.cookies.get(sessions.SESSION_COOKIE))
    session.commit()
    response = JSONResponse(ok({"signed_out": True}))
    response.delete_cookie(
        sessions.SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_https(request),
    )
    if revoked:
        log.info("auth.signout")
    return response
