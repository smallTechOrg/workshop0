"""`/api/admin/network/*` — the admin trainer pool (spec/api.md §Phase 11 Admin pool).

Gate: `auth.deps.require_admin` (a valid `X-Admin-Key` **or** an admin session). It is the
router dependency and also the per-endpoint `actor` dependency — FastAPI caches it per
request, so it runs once and the AdminActor's `by` lands in every audit row.

Thin HTTP layer: queries, validation, audit and logging live in services/pool.py and
services/invites.py.
"""

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, ok, request_base_url, utcnow
from src.workshop0.auth.deps import AdminActor, require_admin
from src.workshop0.db.session import get_session
from src.workshop0.db.models import NetworkInvite
from src.workshop0.email import sender
from src.workshop0.services import invites, matching, pool
from src.workshop0.services.invites import InviteCreate
from src.workshop0.services.opportunities import parse_path_id
from src.workshop0.services.pool import NoteCreate, TagsReplace, TrainerFilters
from src.workshop0.storage import blobstore

router = APIRouter(prefix="/api/admin/network", dependencies=[Depends(require_admin)])

CV_MISSING_MESSAGE = "This trainer's CV file is missing from storage."


def _bad(message: str):
    return api_error("validation_error", message, 422)


def _iso_date(name: str, raw: str | None) -> date | None:
    if raw is None or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        raise _bad(f"{name}: use a YYYY-MM-DD date") from None


def _filters(
    q: str | None = Query(default=None, max_length=200),
    topic: list[str] = Query(default=[]),
    verified: bool | None = Query(default=None),
    tag: str | None = Query(default=None, max_length=40),
    min_level: str | None = Query(default=None),
    budget_max: int | None = Query(default=None, ge=0),
    currency: str | None = Query(default=None),
    unit: str | None = Query(default=None),
    available_start: str | None = Query(default=None),
    available_end: str | None = Query(default=None),
    location_mode: str | None = Query(default=None),
    city: str | None = Query(default=None, max_length=80),
    session: Session = Depends(get_session),
) -> TrainerFilters:
    """Phase-12 rule filters are resolved to an id set by services/matching (None = not used)."""
    min_level = (min_level or "").strip().lower() or None
    currency = (currency or "").strip().upper() or None
    unit = (unit or "").strip().lower() or None
    location_mode = (location_mode or "").strip().lower() or None
    city = (city or "").strip() or None
    start, end = _iso_date("available_start", available_start), _iso_date("available_end", available_end)
    if min_level is not None and min_level not in matching.LEVEL_RANK:
        raise _bad("min_level: must be intermediate, advanced or expert")
    if location_mode is not None and location_mode not in matching.LOCATION_MODES:
        raise _bad("location_mode: must be remote, onsite or hybrid")
    if budget_max is not None:
        if currency not in matching.BUDGET_CURRENCIES or unit not in matching.BUDGET_UNITS:
            raise _bad("budget_max: also send currency (INR|USD) and unit (hour|day|course|month)")
    if start and end and end < start:
        raise _bad("available_end: must not be before available_start")
    ids = None
    if any([min_level, budget_max is not None, start, end, location_mode, city]):
        ids = matching.pool_filter_ids(
            session,
            topics=list(topic),
            min_level=min_level,
            budget_max=budget_max,
            currency=currency,
            unit=unit,
            available_start=start,
            available_end=end,
            location_mode=location_mode,
            city=city,
        )
    return TrainerFilters(q=q, topics=list(topic), verified=verified, tag=tag, profile_ids=ids)


def _profile_id(raw: str) -> int:
    return parse_path_id(raw, pool.NOT_FOUND_MESSAGE)


@router.get("/trainers")
def list_trainers(
    filters: TrainerFilters = Depends(_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    return ok(pool.list_trainers(session, filters, page=page, page_size=page_size))


@router.get("/trainers.csv")
def export_trainers_csv(
    filters: TrainerFilters = Depends(_filters), session: Session = Depends(get_session)
) -> Response:
    body = pool.export_csv(session, filters)
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{pool.csv_filename()}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/trainers/{trainer_id}")
def get_trainer(trainer_id: str, session: Session = Depends(get_session)) -> dict:
    return ok(pool.get_trainer(session, _profile_id(trainer_id)))


@router.get("/trainers/{trainer_id}/cv")
def download_cv(
    trainer_id: str,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> Response:
    download = pool.prepare_cv_download(session, _profile_id(trainer_id), by=actor.by)
    if download.storage_key is None:
        response: Response = Response(
            content=(download.text or "").encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": blobstore.content_disposition(download.filename),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    else:
        try:
            response = blobstore.get_blobstore().download_response(
                download.storage_key, download.filename
            )
        except (blobstore.BlobNotFound, blobstore.InvalidBlobKey):
            session.rollback()
            raise api_error("not_found", CV_MISSING_MESSAGE, 404) from None
    session.commit()  # the cv.download audit row lands only with a real response
    return response


@router.post("/trainers/{trainer_id}/verify")
def verify_trainer(
    trainer_id: str,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    return ok(pool.set_verified(session, _profile_id(trainer_id), verified=True, by=actor.by))


@router.post("/trainers/{trainer_id}/unverify")
def unverify_trainer(
    trainer_id: str,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    return ok(pool.set_verified(session, _profile_id(trainer_id), verified=False, by=actor.by))


@router.post("/trainers/{trainer_id}/notes")
def add_note(
    trainer_id: str,
    body: NoteCreate,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    return ok(pool.add_note(session, _profile_id(trainer_id), body, by=actor.by))


@router.put("/trainers/{trainer_id}/tags")
def set_tags(
    trainer_id: str,
    body: TagsReplace,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    return ok(pool.set_tags(session, _profile_id(trainer_id), body, by=actor.by))


@router.get("/invites")
def list_invites(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    return ok(
        invites.list_invites(
            session, base_url=request_base_url(request), page=page, page_size=page_size
        )
    )


@router.post("/invites")
def create_invite(
    body: InviteCreate,
    request: Request,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    invite, reused = invites.create_invite(
        session, body, by=actor.by, base_url=request_base_url(request)
    )
    return ok({"invite": invite, "reused": reused})


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(
    invite_id: str,
    request: Request,
    actor: AdminActor = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    invite = invites.revoke_invite(
        session,
        parse_path_id(invite_id, "No invite with that id."),
        by=actor.by,
        base_url=request_base_url(request),
    )
    return ok({"invite": invite})


@router.post("/invites/{invite_id}/email")
def email_invite(
    invite_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    """Explicit per-invite click: enqueue one `network.invite` mail (never automatic or bulk).
    The dedupe + `invite.email` audit row (once per outbox row) live in `email.sender`."""
    invite = session.get(NetworkInvite, parse_path_id(invite_id, "No invite with that id."))
    if invite is None:
        raise api_error("not_found", "No invite with that id.", 404)
    sibling = bool(invites._accepted_emails(session, {invite.email}))
    status = invites.invite_status(invite, utcnow(), sibling_accepted=sibling)
    refusal = {
        "revoked": ("invite_revoked", "This invite was revoked, so it can't be emailed."),
        "accepted": ("invite_used", "This invite was already used, so it can't be emailed."),
        "superseded": ("invite_used", "This person already joined through another invite."),
        "expired": ("invite_expired", "This invite has expired - refresh it before emailing."),
    }.get(status)
    if refusal is not None:
        raise api_error(refusal[0], refusal[1], 409)
    row = sender.enqueue_invite_email(session, invite, request_base_url(request))
    session.commit()
    sender.schedule_drain(background_tasks)
    session.refresh(row)
    return ok({"outbox": {"id": row.id, "status": row.status}})


@router.get("/ai-spend")
def ai_spend(session: Session = Depends(get_session)) -> dict:
    return ok(pool.network_ai_spend(session))
