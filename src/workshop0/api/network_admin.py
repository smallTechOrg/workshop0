"""`/api/admin/network/*` — the admin trainer pool (spec/api.md §Phase 11 Admin pool).

Gate: `auth.deps.require_admin` (a valid `X-Admin-Key` **or** an admin session). It is the
router dependency and also the per-endpoint `actor` dependency — FastAPI caches it per
request, so it runs once and the AdminActor's `by` lands in every audit row.

Thin HTTP layer: queries, validation, audit and logging live in services/pool.py and
services/invites.py.
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from src.workshop0.api._common import api_error, ok, request_base_url
from src.workshop0.auth.deps import AdminActor, require_admin
from src.workshop0.db.session import get_session
from src.workshop0.services import invites, pool
from src.workshop0.services.invites import InviteCreate
from src.workshop0.services.opportunities import parse_path_id
from src.workshop0.services.pool import NoteCreate, TagsReplace, TrainerFilters
from src.workshop0.storage import blobstore

router = APIRouter(prefix="/api/admin/network", dependencies=[Depends(require_admin)])

CV_MISSING_MESSAGE = "This trainer's CV file is missing from storage."


def _filters(
    q: str | None = Query(default=None, max_length=200),
    topic: list[str] = Query(default=[]),
    verified: bool | None = Query(default=None),
    tag: str | None = Query(default=None, max_length=40),
) -> TrainerFilters:
    return TrainerFilters(q=q, topics=list(topic), verified=verified, tag=tag)


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
    invite = invites.create_invite(session, body, by=actor.by, base_url=request_base_url(request))
    return ok({"invite": invite})


@router.get("/ai-spend")
def ai_spend(session: Session = Depends(get_session)) -> dict:
    return ok(pool.network_ai_spend(session))
