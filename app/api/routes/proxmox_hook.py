"""Endpoint webhook Proxmox VE — recoit les notifications et les dispatche
vers les templates configures dans BotPanel.

Configuration Proxmox (Datacenter → Notifications → Webhook) :
  URL    : http://<IP_LXC>:8080/api/proxmox/backup
  Method : POST
  Header : Authorization: Bearer <PROXMOX_WEBHOOK_SECRET>  (si defini dans .env)
  Body   :
    {
      "severity": "{{ severity }}",
      "title":    "{{ title }}",
      "body":     "{{ message }}",
      "hostname": "{{ hostname }}"
    }

Placeholders utilisables dans les templates BotPanel :
  {px:vmid}      VM/CT ID
  {px:hostname}  Nœud Proxmox
  {px:severity}  Severite (info/warning/error)
  {px:title}     Titre de la notif Proxmox
  {px:body}      Corps de la notif Proxmox
  {px:type}      Type (lxc/qemu)
  {px:storage}   Stockage cible
  {px:duration}  Duree du backup (ex. "2m 34s")
  {px:size}      Taille du backup (ex. "2.1 Go")
  {px:node}      Alias de {px:hostname}
"""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

import discord
from fastapi import APIRouter, HTTPException, Request

from app.bot.notifications import _resolve_channel
from app.config import settings
from app.db.models import ProxmoxNotification
from app.db.repositories import ProxmoxNotificationRepository

logger = logging.getLogger(__name__)
router = APIRouter()

_PX_RE = re.compile(r"\{px:([a-zA-Z0-9_]+)\}")

_SEVERITY_MAP: dict[str, str] = {
    "info": "info",
    "information": "info",
    "success": "info",
    "ok": "info",
    "warning": "warning",
    "warn": "warning",
    "error": "error",
    "critical": "error",
    "fatal": "error",
    "failure": "error",
    "failed": "error",
}

_COLORS: dict[str, int] = {
    "info":    0x4ADE80,
    "warning": 0xF59E0B,
    "error":   0xEF4444,
}

_FR_MONTHS = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


def _human_size(raw: Any) -> str:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024:
            return f"{n} {unit}"
        n //= 1024
    return f"{n} Po"


def _human_duration(raw: Any) -> str:
    try:
        secs = int(raw)
    except (TypeError, ValueError):
        return str(raw)
    h, rest = divmod(secs, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _build_px_context(payload: dict[str, Any]) -> dict[str, str]:
    """Construit le dictionnaire de remplacement des placeholders {px:...}."""
    severity = _SEVERITY_MAP.get(str(payload.get("severity", "")).lower(), "info")
    duration_raw = payload.get("duration") or payload.get("elapsed")
    size_raw = payload.get("size") or payload.get("backup_size")
    hostname = str(payload.get("hostname") or payload.get("node") or "—")
    return {
        "vmid":     str(payload.get("vmid") or payload.get("vm_id") or "—"),
        "hostname": hostname,
        "node":     hostname,
        "severity": severity,
        "title":    str(payload.get("title") or ""),
        "body":     str(payload.get("body") or payload.get("message") or ""),
        "type":     str(payload.get("type") or payload.get("vm_type") or "—").upper(),
        "storage":  str(payload.get("storage") or payload.get("storage_id") or "—"),
        "duration": _human_duration(duration_raw) if duration_raw is not None else "—",
        "size":     _human_size(size_raw) if size_raw is not None else "—",
    }


def _resolve_px(text: str, ctx: dict[str, str]) -> str:
    return _PX_RE.sub(lambda m: ctx.get(m.group(1), f"{{px:{m.group(1)}}}"), text)


def _format_fr_dt() -> str:
    import datetime as dt
    now = dt.datetime.now()
    return f"{now.day} {_FR_MONTHS[now.month - 1]} {now.year} a {now:%H:%M}"


async def send_proxmox_notification(
    notif: ProxmoxNotification, payload: dict[str, Any]
) -> int:
    """Resout les placeholders et envoie l'embed Discord.

    Retourne 1 si envoye, 0 si echec.
    """
    ctx = _build_px_context(payload)

    title = _resolve_px(notif.title, ctx)
    message = _resolve_px(notif.message, ctx)

    embed = discord.Embed(title=title, description=message or None, color=notif.color)

    if notif.icon_url:
        embed.set_thumbnail(url=notif.icon_url)

    for fld in sorted(notif.fields, key=lambda f: (f.position, f.id or 0)):
        value = _resolve_px(fld.value_template, ctx)
        embed.add_field(name=fld.name, value=value or "​", inline=fld.inline)

    footer_parts: list[str] = []
    if notif.footer:
        footer_parts.append(_resolve_px(notif.footer, ctx))
    if notif.show_timestamp:
        footer_parts.append(_format_fr_dt())
    if footer_parts:
        embed.set_footer(text=" · ".join(footer_parts))

    channel = await _resolve_channel(
        str(settings.proxmox_webhook_channel_id or settings.discord_default_channel_id)
        if not notif.channel_id
        else notif.channel_id
    )
    if channel is None:
        logger.error("Proxmox : channel %s introuvable pour la notification %s", notif.channel_id, notif.id)
        return 0

    try:
        await channel.send(embed=embed)
        return 1
    except discord.HTTPException as exc:
        logger.error("Proxmox : echec envoi Discord (notif %s) : %s", notif.id, exc)
        return 0


@router.post("/proxmox/backup")
async def proxmox_backup_webhook(request: Request) -> dict[str, Any]:
    """Recoit un webhook Proxmox VE et dispatch vers les templates actives."""

    # Auth optionnelle
    if settings.proxmox_webhook_secret:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not token or not secrets.compare_digest(token, settings.proxmox_webhook_secret):
            logger.warning("Webhook Proxmox : token invalide depuis %s", request.client)
            raise HTTPException(status_code=401, detail="Token invalide")

    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON invalide")

    logger.debug("Webhook Proxmox recu : %s", payload)

    severity = _SEVERITY_MAP.get(str(payload.get("severity", "")).lower(), "info")

    repo = ProxmoxNotificationRepository()
    templates = await repo.list_by_event(severity)

    if not templates:
        logger.info("Webhook Proxmox [%s] : aucun template actif", severity)
        return {"status": "no_template", "severity": severity, "sent": 0}

    sent = 0
    for notif in templates:
        sent += await send_proxmox_notification(notif, payload)

    logger.info(
        "Webhook Proxmox [%s] '%s' : %d/%d envoye(s)",
        severity, payload.get("title", "—"), sent, len(templates),
    )
    return {"status": "sent", "severity": severity, "sent": sent, "total": len(templates)}
