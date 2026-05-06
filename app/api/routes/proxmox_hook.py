"""Endpoint pour les webhooks Proxmox VE (notifications de backup).

Proxmox VE 8.1+ peut envoyer des webhooks via Datacenter -> Notifications.
Configurer un endpoint de type "Webhook" avec :
  URL    : http://<IP_LXC>:8080/api/proxmox/backup
  Method : POST
  Header : Authorization: Bearer <PROXMOX_WEBHOOK_SECRET>  (si defini)
  Body   :
    {
      "severity": "{{ severity }}",
      "title":    "{{ title }}",
      "body":     "{{ message }}",
      "hostname": "{{ hostname }}"
    }

Pour les anciens Proxmox (vzdump hook script), envoyer le meme format via curl.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

import discord
from fastapi import APIRouter, HTTPException, Request

from app.bot.notifications import _resolve_channel
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Couleurs Discord par severite
_COLORS: dict[str, int] = {
    "info":    0x4ADE80,   # vert
    "warning": 0xF59E0B,   # orange/jaune
    "error":   0xEF4444,   # rouge
    "unknown": 0x6B7280,   # gris
}

# Icones par severite
_ICONS: dict[str, str] = {
    "info":    "✅",
    "warning": "⚠️",
    "error":   "❌",
    "unknown": "🔔",
}


def _normalize_severity(raw: str) -> str:
    raw = raw.lower().strip()
    if raw in ("info", "information", "success", "ok"):
        return "info"
    if raw in ("warning", "warn"):
        return "warning"
    if raw in ("error", "critical", "fatal", "failure", "failed"):
        return "error"
    return "unknown"


def _human_size(value: Any) -> str:
    """Convertit une taille en octets en chaine lisible."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} Po"


def _build_embed(payload: dict[str, Any]) -> discord.Embed:
    severity = _normalize_severity(str(payload.get("severity", "unknown")))
    color = _COLORS[severity]
    icon = _ICONS[severity]

    raw_title = payload.get("title") or "Backup Proxmox"
    title = f"{icon} {raw_title}"

    body = (
        payload.get("body")
        or payload.get("message")
        or payload.get("description")
        or ""
    )

    embed = discord.Embed(title=title, color=color)
    if body:
        embed.description = str(body)[:4096]

    # Champs optionnels (metadata backup)
    fields: list[tuple[str, str]] = []

    vmid = payload.get("vmid") or payload.get("vm_id")
    if vmid is not None:
        fields.append(("VM / CT", str(vmid)))

    hostname = payload.get("hostname") or payload.get("node")
    if hostname:
        fields.append(("Nœud", str(hostname)))

    vmtype = payload.get("type") or payload.get("vm_type")
    if vmtype:
        fields.append(("Type", str(vmtype).upper()))

    duration = payload.get("duration") or payload.get("elapsed")
    if duration is not None:
        try:
            secs = int(duration)
            h, remainder = divmod(secs, 3600)
            m, s = divmod(remainder, 60)
            if h:
                human = f"{h}h {m:02d}m {s:02d}s"
            elif m:
                human = f"{m}m {s:02d}s"
            else:
                human = f"{s}s"
        except (TypeError, ValueError):
            human = str(duration)
        fields.append(("Durée", human))

    size = payload.get("size") or payload.get("backup_size")
    if size is not None:
        fields.append(("Taille", _human_size(size)))

    storage = payload.get("storage") or payload.get("storage_id")
    if storage:
        fields.append(("Stockage", str(storage)))

    for name, value in fields:
        embed.add_field(name=name, value=value, inline=True)

    embed.set_footer(text="Proxmox VE · BotPanel")
    embed.timestamp = discord.utils.utcnow()

    return embed


@router.post("/proxmox/backup")
async def proxmox_backup_webhook(request: Request) -> dict[str, str]:
    """Recoit un webhook Proxmox VE et envoie une notification Discord.

    Authentification optionnelle via header Authorization: Bearer <secret>.
    Configurer PROXMOX_WEBHOOK_SECRET dans .env pour l'activer.
    """
    # --- Auth optionnelle ---
    if settings.proxmox_webhook_secret:
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        if not token or not secrets.compare_digest(token, settings.proxmox_webhook_secret):
            logger.warning("Webhook Proxmox : token invalide depuis %s", request.client)
            raise HTTPException(status_code=401, detail="Token invalide")

    # --- Payload ---
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON invalide")

    logger.debug("Webhook Proxmox recu : %s", payload)

    # --- Construction de l'embed ---
    embed = _build_embed(payload)

    # --- Envoi Discord ---
    channel_id = str(
        settings.proxmox_webhook_channel_id
        if settings.proxmox_webhook_channel_id
        else settings.discord_default_channel_id
    )
    channel = await _resolve_channel(channel_id)
    if channel is None:
        logger.error("Webhook Proxmox : channel %s introuvable", channel_id)
        raise HTTPException(status_code=500, detail=f"Channel Discord {channel_id} introuvable")

    try:
        await channel.send(embed=embed)
    except discord.HTTPException as exc:
        logger.error("Webhook Proxmox : echec envoi Discord : %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    severity = _normalize_severity(str(payload.get("severity", "unknown")))
    title = payload.get("title", "—")
    logger.info("Webhook Proxmox traite : [%s] %s", severity, title)
    return {"status": "sent"}
