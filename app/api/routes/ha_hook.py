"""Endpoint appele par Home Assistant via rest_command.

HA fait un POST /api/notify avec un payload { "id": "<slug>" } pour declencher
l'envoi de la notification correspondante.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.bot.notifications import send_notification

logger = logging.getLogger(__name__)
router = APIRouter()


class NotifyPayload(BaseModel):
    id: str  # slug de la notification
    # Variables dynamiques optionnelles : remplissent les {var:nom} du template.
    # Ex: {"vmid": "100", "duree": "2m34s"}
    vars: Optional[dict] = None


@router.post("/notify")
async def notify(payload: NotifyPayload) -> dict[str, str]:
    """Declenche l'envoi d'une notification Discord.

    Appele par HA ou n'importe quel projet :
        POST /api/notify
        { "id": "notif_porte_entree" }

    Avec variables dynamiques (remplissent les {var:nom} du template) :
        { "id": "backup_done", "vars": { "vmid": "100", "duree": "2m34s" } }
    """
    message = await send_notification(payload.id, payload.vars)
    if message is None:
        raise HTTPException(status_code=404, detail=f"Notification '{payload.id}' introuvable ou echec d'envoi")
    return {"status": "sent", "message_id": str(message.id)}
