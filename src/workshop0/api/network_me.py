"""`/api/me/*` — trainer self-service: CV, draft, profile, deletion (spec/api.md §Phase 11).

Every endpoint is guarded by `auth.deps.require_user` (401 `not_signed_in`; on non-GET also
403 `csrf_failed` without `X-Requested-With: workshop0`). Thin HTTP layer — the rules live in
services/profiles.py. Mutations commit before responding; the CV drafter runs as a
BackgroundTask only after the commit, so it always sees the new cv_document row.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Request, Response, UploadFile
from sqlalchemy.orm import Session

from src.workshop0.api._common import ok, request_base_url
from src.workshop0.auth.deps import CurrentUser, require_user
from src.workshop0.db.session import create_db_session, get_session
from src.workshop0.auth.routes import clean_invite_token
from src.workshop0.email import sender
from src.workshop0.services import applications, invites, profiles
from src.workshop0.services.profiles import ProfileCreate, ProfilePatch
from src.workshop0.services.ratelimit import enforce, hit

log = structlog.get_logger("workshop0")

router = APIRouter(prefix="/api/me")

SESSION_COOKIE = "workshop0_session"
CV_LIMIT, CV_WINDOW_S = 10, 3600  # CV upload/paste: 10/h/user
DRAFT_LIMIT, DRAFT_WINDOW_S = 600, 3600  # profile drafting: 600/h global (cost guard)
DRAFT_BUCKET = "draft:global"
INVITE_ACCEPT_LIMIT, INVITE_ACCEPT_WINDOW_S = 20, 3600  # direct invite accept: 20/h/user


def _cv_bucket(user_id: int) -> str:
    return f"cv:user:{user_id}"


def _run_draft(cv_document_id: int) -> None:
    """BackgroundTask: the drafter owns DB in/out; a crash never leaves the poll stuck on
    `pending` (the onboarding screen would spin for its full 60 s)."""
    from src.workshop0.ai.profile_draft import run_profile_draft

    try:
        run_profile_draft(cv_document_id)
    except Exception as exc:  # noqa: BLE001 — background work must not raise into the server
        log.error(
            "ai.call_failed", purpose="profile_draft", cause="drafter_crashed", error=type(exc).__name__
        )
        try:
            with create_db_session() as session:
                profiles.mark_draft_failed_if_pending(session, cv_document_id)
        except Exception:  # noqa: BLE001
            log.error("cv.draft_status_update_failed", cv_document_id=cv_document_id)


def _finish_cv(session: Session, background: BackgroundTasks, cv, old_key: str | None) -> dict:
    # Cost guard: past the global drafting budget the CV is still stored and the person
    # continues with an empty form (never blocked) — drafting is skipped.
    if hit(session, DRAFT_BUCKET, DRAFT_LIMIT, DRAFT_WINDOW_S).allowed:
        background.add_task(_run_draft, cv.id)
    else:
        cv.draft_status = "skipped"
    payload = {"cv": profiles.cv_summary(cv)}
    session.commit()
    if old_key:
        from src.workshop0.storage.blobstore import get_blobstore

        profiles.delete_blob(get_blobstore(), old_key)
    return ok(payload)


@router.post("/cv")
def upload_cv(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    enforce(session, _cv_bucket(user.id), CV_LIMIT, CV_WINDOW_S)
    data = file.file.read(profiles.MAX_CV_BYTES + 1)
    upload = profiles.classify_upload(data, file.filename, file.content_type)

    from src.workshop0.storage.blobstore import get_blobstore

    cv, old_key = profiles.ingest_file(session, get_blobstore(), user.id, upload)
    return _finish_cv(session, background, cv, old_key)


@router.post("/cv/text")
def paste_cv_text(
    background: BackgroundTasks,
    body: dict[str, Any] = Body(...),
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    enforce(session, _cv_bucket(user.id), CV_LIMIT, CV_WINDOW_S)
    text = profiles.validate_pasted_text(body.get("text"))
    cv, old_key = profiles.ingest_text(session, user.id, text)
    return _finish_cv(session, background, cv, old_key)


@router.get("/cv/draft")
def get_draft(
    user: CurrentUser = Depends(require_user), session: Session = Depends(get_session)
) -> dict:
    return ok(profiles.draft_state(session, user.id))


@router.get("/cv/file")
def download_cv(
    user: CurrentUser = Depends(require_user), session: Session = Depends(get_session)
) -> Response:
    cv = profiles.own_cv(session, user.id)
    if cv.storage_key is None:  # pasted text: hand back what they pasted
        return Response(
            content=cv.text_extract.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="cv.txt"'},
        )
    from src.workshop0.storage.blobstore import get_blobstore

    filename = cv.original_filename or f"cv.{cv.source}"
    return get_blobstore().download_response(cv.storage_key, filename)


@router.post("/profile")
def create_profile(
    body: ProfileCreate,
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    payload = profiles.create_profile(session, user.id, body)
    session.commit()
    return ok(payload)


@router.get("/profile")
def get_profile(
    user: CurrentUser = Depends(require_user), session: Session = Depends(get_session)
) -> dict:
    return ok(profiles.read_own(session, user.id))


@router.patch("/profile")
def patch_profile(
    body: ProfilePatch,
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    payload = profiles.update_profile(session, user.id, body)
    session.commit()
    return ok(payload)


@router.delete("")
def delete_account(
    response: Response,
    body: dict[str, Any] = Body(...),
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    blob_key = profiles.delete_account(session, user.id, body.get("confirm_email"))
    session.commit()
    if blob_key:
        from src.workshop0.storage.blobstore import get_blobstore

        profiles.delete_blob(get_blobstore(), blob_key)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return ok({"deleted": True})


@router.post("/invite/accept")
def accept_invite(
    body: dict[str, Any] = Body(default_factory=dict),
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    """Phase 11d: apply an invite to the signed-in user without a second Google round-trip
    (api.md §Phase 11d). Same checks as the callback, with the session user's email."""
    enforce(session, f"invite_accept:user:{user.id}", INVITE_ACCEPT_LIMIT, INVITE_ACCEPT_WINDOW_S)
    raw = body.get("token") if isinstance(body, dict) else None
    token = clean_invite_token(raw) if isinstance(raw, str) else None
    return ok(invites.accept_for_user(session, token, user))


# --------------------------------------------------------------------------- Phase 12


@router.post("/applications")
def apply_to_opportunity(
    body: applications.ApplyBody,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    enforce(session, f"apply:user:{user.id}", applications.APPLY_LIMIT, applications.APPLY_WINDOW_S)
    payload = applications.apply(session, user.id, body, base_url=request_base_url(request))
    session.commit()
    sender.schedule_drain(background)
    return ok({"application": payload})


@router.get("/applications")
def my_applications(
    request: Request,
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    return ok(applications.list_mine(session, user.id, base_url=request_base_url(request)))


@router.post("/applications/{application_id}/withdraw")
def withdraw_application(
    application_id: int,
    request: Request,
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    payload = applications.withdraw(
        session, user.id, application_id, base_url=request_base_url(request)
    )
    session.commit()
    return ok({"application": payload})


@router.get("/matches")
def matched_for_you(
    request: Request,
    user: CurrentUser = Depends(require_user),
    session: Session = Depends(get_session),
) -> dict:
    return ok(applications.matches(session, user.id, base_url=request_base_url(request)))
