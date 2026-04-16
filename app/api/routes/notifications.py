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
