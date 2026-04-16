"""Endpoint appele par Home Assistant via rest_command.

HA fait un POST /api/notify avec un payload { "id": "<slug>" } pour declencher
l'envoi de la notification correspondante.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.bot.notifications import send_notification

logger = logging.getLogger(__name__)
router = APIRouter()


class NotifyPayload(BaseModel):
    id: str  # slug de la notification


@router.post("/notify")
async def notify(payload: NotifyPayload) -> dict[str, str]:
    """Declenche l'envoi d'une notification Discord.

    Appele par HA :
        service: rest_command.bot_discord
        data:
          id: "notif_porte_entree"
    """
    message = await send_notification(payload.id)
    if message is None:
        raise HTTPException(status_code=404, detail=f"Notification '{payload.id}' introuvable ou echec d'envoi")
    return {"status": "sent", "message_id": str(message.id)}
