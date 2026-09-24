"""API machine pour l'integration Home Assistant.

Toutes ces routes sont protegees par la cle API (X-API-Key), verifiee en amont
dans le garde (`app/api/server.py`). Elles ne dependent JAMAIS du login humain.

- GET  /api/integration/ping           -> identite + version (validation config HA)
- GET  /api/integration/notifications  -> liste des notifs (boutons + action HA)
- GET  /api/integration/state          -> capteurs (bot en ligne, envois, ...)
- POST /api/integration/trigger        -> declenche une notif par id ou slug
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.repositories import LogRepository, NotificationRepository

logger = logging.getLogger(__name__)
router = APIRouter()

VERSION = "1.0.0"


class TriggerIn(BaseModel):
    id: int | None = None
    slug: str | None = None


@router.get("/ping")
async def ping() -> dict:
    """Identite du serveur (sert a valider l'URL + la cle cote Home Assistant)."""
    return {"name": "BotPanel", "version": VERSION, "ok": True}


@router.get("/notifications")
async def list_for_integration() -> list[dict]:
    """Liste compacte des notifications (pour construire boutons + autocompletion)."""
    notifs = await NotificationRepository().list_all()
    return [
        {"id": n.id, "slug": n.slug, "title": n.title, "group": n.list_group or ""}
        for n in notifs
    ]


@router.get("/state")
async def integration_state() -> dict:
    """Etat expose a Home Assistant (capteurs lecture seule)."""
    # Import differe : evite de charger discord si le bot n'est pas necessaire.
    try:
        from app.bot.client import bot
        bot_online = bool(bot.is_ready())
    except Exception:  # noqa: BLE001
        bot_online = False

    log_repo = LogRepository()
    today = await log_repo.stats_today()
    total = await log_repo.count_sends_total()
    last = await log_repo.last_send()
    notif_count = await NotificationRepository().count_all()

    return {
        "bot_online": bot_online,
        "sent_today": today["sent_ok"],
        "sent_total": total,
        "notif_count": notif_count,
        "last_alert": last,  # {slug, created_at, source} ou None
    }


@router.post("/trigger")
async def trigger(payload: TriggerIn) -> dict:
    """Declenche une notification par `id` ou `slug` (origine = home_assistant)."""
    from app.bot.notifications import send_notification

    slug = payload.slug
    if slug is None and payload.id is not None:
        notif = await NotificationRepository().get_by_id(payload.id)
        if notif is None:
            raise HTTPException(404, "Notification introuvable")
        slug = notif.slug
    if not slug:
        raise HTTPException(422, "Fournis un id ou un slug de notification.")

    msg = await send_notification(slug, source="home_assistant")
    if msg is None:
        raise HTTPException(500, "Echec d'envoi (voir logs)")
    return {"status": "sent", "slug": slug, "message_id": str(msg.id)}
