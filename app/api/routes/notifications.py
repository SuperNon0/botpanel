"""CRUD des notifications."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.db.models import Notification, NotificationIn
from app.db.repositories import NotificationRepository

router = APIRouter()
repo = NotificationRepository()


@router.get("", response_model=list[Notification])
async def list_notifications() -> list[Notification]:
    return await repo.list_all()


@router.post("", response_model=Notification, status_code=201)
async def create_notification(payload: NotificationIn) -> Notification:
    existing = await repo.get_by_slug(payload.slug)
    if existing is not None:
        raise HTTPException(409, f"slug '{payload.slug}' deja utilise")
    return await repo.create(payload)


@router.get("/{notif_id}", response_model=Notification)
async def get_notification(notif_id: int) -> Notification:
    notif = await repo.get_by_id(notif_id)
    if notif is None:
        raise HTTPException(404, "Notification introuvable")
    return notif


@router.put("/{notif_id}", response_model=Notification)
async def update_notification(notif_id: int, payload: NotificationIn) -> Notification:
    # Verifie l'unicite du slug (si on le change)
    by_slug = await repo.get_by_slug(payload.slug)
    if by_slug is not None and by_slug.id != notif_id:
        raise HTTPException(409, f"slug '{payload.slug}' deja utilise")
    notif = await repo.update(notif_id, payload)
    if notif is None:
        raise HTTPException(404, "Notification introuvable")
    return notif


@router.delete("/{notif_id}", status_code=204, response_class=Response)
async def delete_notification(notif_id: int):
    ok = await repo.delete(notif_id)
    if not ok:
        raise HTTPException(404, "Notification introuvable")
    return Response(status_code=204)


@router.post("/{notif_id}/test", status_code=202)
async def test_notification(notif_id: int) -> dict[str, str]:
    """Envoie la notification pour test."""
    from app.bot.notifications import send_notification

    notif = await repo.get_by_id(notif_id)
    if notif is None:
        raise HTTPException(404, "Notification introuvable")
    msg = await send_notification(notif.slug)
    if msg is None:
        raise HTTPException(500, "Echec d'envoi (voir logs)")
    return {"status": "sent", "message_id": str(msg.id)}


@router.post("/preview", status_code=202)
async def preview_notification(
    payload: NotificationIn,
    as_id: int | None = None,
) -> dict[str, str]:
    """Envoie une notification non persistee pour test depuis l'editeur.

    Si `as_id` est fourni (= edition d'une notif existante), on reutilise
    cet ID + les IDs des boutons par position pour que les clics fonctionnent
    (ils executeront la version SAUVEGARDEE de l'action).
    Sinon, les boutons sont en mode "preview" et repondent en ephemere.
    """
    from app.bot.notifications import send_notification_object

    notif_id = 0
    saved_button_ids: list[int | None] = []
    if as_id is not None:
        existing = await repo.get_by_id(as_id)
        if existing is not None:
            notif_id = existing.id
            saved_button_ids = [b.id for b in existing.buttons]

    # On reconstruit la notif a partir du payload, mais en injectant les IDs
    # sauvegardes sur les boutons par position.
    payload_dict = payload.model_dump()
    for idx, btn in enumerate(payload_dict.get("buttons", [])):
        if idx < len(saved_button_ids) and saved_button_ids[idx] is not None:
            btn["id"] = saved_button_ids[idx]
    ephemeral = Notification(id=notif_id, **payload_dict)

    msg = await send_notification_object(ephemeral)
    if msg is None:
        raise HTTPException(500, "Echec d'envoi (voir logs)")
    return {"status": "sent", "message_id": str(msg.id)}


@router.post("/{notif_id}/duplicate", response_model=Notification, status_code=201)
async def duplicate_notification(notif_id: int) -> Notification:
    """Duplique une notification existante (slug `<original>_copy`).

    Si le slug `_copy` existe deja, on incremente : `_copy2`, `_copy3`, ...
    """
    src = await repo.get_by_id(notif_id)
    if src is None:
        raise HTTPException(404, "Notification introuvable")

    # Trouve un slug libre
    base = f"{src.slug}_copy"
    slug = base
    n = 2
    while await repo.get_by_slug(slug) is not None:
        slug = f"{base}{n}"
        n += 1

    payload = NotificationIn(
        **{**src.model_dump(exclude={"id"}), "slug": slug, "title": f"{src.title} (copie)"}
    )
    return await repo.create(payload)
