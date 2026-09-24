"""API machine pour l'integration Home Assistant.

Toutes ces routes sont protegees par la cle API (X-API-Key), verifiee en amont
dans le garde (`app/api/server.py`). Elles ne dependent JAMAIS du login humain.

- GET  /api/integration/ping           -> identite + version (validation config HA)
- GET  /api/integration/notifications  -> liste des notifs (boutons + action HA)
- GET  /api/integration/state          -> capteurs (bot en ligne, envois, ...)
- POST /api/integration/trigger        -> declenche une notif par id ou slug
"""
from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.repositories import LogRepository, NotificationRepository

logger = logging.getLogger(__name__)
router = APIRouter()

VERSION = "1.0.0"

_COLOR_ERROR = 0xE85C47    # rouge — override auto sur erreur
_COLOR_WARNING = 0xE87C47  # orange — override auto sur avertissement


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


# ----------------------------------------------------------------------
# Webhook Proxmox / PBS -> notification BotPanel
# ----------------------------------------------------------------------
def parse_proxmox(raw: str, content_type: str = "") -> dict:
    """Extrait des variables exploitables d'un webhook Proxmox / PBS.

    Deux formats acceptes :
      - JSON : {"severity","title","message"} (ou severite/titre)
      - Texte (recommande, robuste) : 3 lignes = severite / titre / message.
    Renvoie toujours au minimum {severite, titre, message, statut}. Les autres
    champs (vmid, nom, duree, taille, datastore) sont extraits « best-effort ».
    """
    raw = (raw or "").strip()
    severite = titre = message = ""

    # On decide du format par le CONTENU, pas par le Content-Type : Proxmox
    # pre-remplit souvent "application/json" meme quand le corps est le texte
    # 3 lignes recommande. On ne tente le JSON que si le corps ressemble a du JSON.
    looks_json = raw.startswith("{") or raw.startswith("[")
    parsed = False
    if looks_json:
        try:
            j = json.loads(raw)
            severite = str(j.get("severity") or j.get("severite") or "").strip()
            titre = str(j.get("title") or j.get("titre") or "").strip()
            message = str(j.get("message") or j.get("text") or "").strip()
            parsed = True
        except Exception:  # noqa: BLE001
            parsed = False
    if not parsed:
        lines = raw.split("\n")
        severite = lines[0].strip() if lines else ""
        titre = lines[1].strip() if len(lines) > 1 else ""
        message = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""

    # Gravite : d'abord le champ severity, complete par des mots-cles du titre
    # (Proxmox met "backup successful" / "backup failed" dans le titre).
    sev = severite.lower()
    tl = titre.lower()
    is_error = sev in ("error", "err", "critical", "alert") or "fail" in tl
    is_warn = (not is_error) and (sev in ("warning", "warn") or "warn" in tl)
    statut = "❌ Erreur" if is_error else ("⚠️ Avertissement" if is_warn else "✅ OK")

    def _first(*patterns: str) -> str:
        """Renvoie la 1re capture non vide en essayant les motifs dans l'ordre."""
        for pat in patterns:
            m = re.search(pat, message, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
        return ""

    # Motifs calés sur un vrai backup vzdump PVE (+ repli generique).
    vmid = _first(
        r"Backup of VM\s+([0-9]{2,})",
        r"backup-id[ =]+([0-9]{2,})",
        r"\bVM\s+([0-9]{2,})\b",
        r"\b(?:vmid|ct|guest)[\s:=#]*([0-9]{2,})",
    )
    nom = _first(
        r"(?:CT|VM)\s+Name:\s*([^\n]+)",          # ligne de log fiable (« CT Name: Cine »)
        r"\b(?:hostname|guest[\s-]*name)[\s:=]+([^\n,;]+)",
    )
    duree = _first(
        r"(?:Total running time|running time|duration|dur[ée]e|total time)[ \t:=]+([0-9][0-9hms:\.,]*)",
        r"Finished Backup of VM[^\n(]*\(([0-9:]+)\)",   # « (00:00:33) »
    )
    taille = _first(
        r"Total size[ \t:=]+([0-9][0-9\.,]*\s?[KMGT]i?B)",
        r"([0-9][0-9\.,]*\s?[KMGT]i?B)",
    )
    datastore = _first(
        r"--storage\s+(\S+)",                     # commande vzdump (« --storage pbs-local »)
        r"\b(?:datastore|storage)[\s:=]+([^\s,;'\"]+)",
    )

    data = {
        "severite": severite,
        "titre": titre,
        "message": message,
        "statut": statut,
        "vmid": vmid,
        "nom": nom,
        "duree": duree,
        "taille": taille,
        "datastore": datastore,
    }
    data["_is_error"] = is_error
    data["_is_warn"] = is_warn
    return data


# Une ligne du tableau « Details » d'un backup vzdump :
#   VMID  Name  Status  Time  Size            Filename
#   108   Cine  ok      33s   1.021 GiB       ct/108/2026-...
_VM_ROW_RE = re.compile(
    r"^\s*(\d{2,})\s+(\S+)\s+(\w+)\s+(\S+)\s+"
    r"([0-9][0-9.,]*\s*[KMGTP]i?B|0\s*B|-)\s+\S+",
    re.MULTILINE,
)


def proxmox_vm_rows(message: str) -> list[dict]:
    """Extrait une entree par VM depuis le tableau « Details » (multi-VM).

    Renvoie [] si aucun tableau (ex. PBS sync) -> l'appelant retombe sur l'envoi
    unique classique.
    """
    rows: list[dict] = []
    for m in _VM_ROW_RE.finditer(message or ""):
        vmid, nom, status, duree, taille = m.groups()
        st = status.lower()
        rows.append(
            {
                "vmid": vmid,
                "nom": nom,
                "duree": duree.strip(),
                "taille": taille.strip(),
                "_ok": st in ("ok", "done", "success", "successful"),
            }
        )
    return rows


def proxmox_resume(rows: list[dict]) -> str:
    """Construit un tableau recap compact : une ligne courte par VM.

    Ex. « ✅ 108 · Cine · 33s · 1.021 GiB ». Vide s'il n'y a pas de tableau
    (ex. PBS sync). Reste tres court meme avec beaucoup de VMs.
    """
    lines = []
    for r in rows:
        emoji = "✅" if r["_ok"] else "❌"
        parts = [r["vmid"], r.get("nom", ""), r.get("duree", ""), r.get("taille", "")]
        parts = [p for p in parts if p]
        lines.append(f"{emoji} " + " · ".join(parts))
    return "\n".join(lines)


@router.post("/proxmox/{slug}")
async def proxmox_webhook(slug: str, request: Request) -> dict:
    """Recoit un webhook Proxmox/PBS et declenche la notification `slug`.

    Le corps (texte ou JSON) est parse en variables {var:...} injectees dans le
    template de la notification. La couleur passe en rouge/orange auto selon la
    gravite. Origine dans l'historique : « proxmox ».
    """
    from app.bot.notifications import send_notification_object

    raw = (await request.body()).decode("utf-8", "replace")
    data = parse_proxmox(raw, request.headers.get("content-type", ""))

    notif = await NotificationRepository().get_by_slug(slug)
    if notif is None:
        raise HTTPException(404, f"Notification '{slug}' introuvable")

    # Tableau recap compact : une ligne courte par VM (multi-VM).
    rows = proxmox_vm_rows(data["message"])
    resume = proxmox_resume(rows)
    any_vm_error = any(not r["_ok"] for r in rows)
    is_error = data["_is_error"] or any_vm_error
    is_warn = data["_is_warn"] and not is_error

    # Override couleur selon la gravite (sans toucher la config sauvegardee).
    target = notif
    if is_error:
        target = notif.model_copy(update={"color": _COLOR_ERROR})
    elif is_warn:
        target = notif.model_copy(update={"color": _COLOR_WARNING})

    variables = {k: v for k, v in data.items() if not k.startswith("_")}
    variables["resume"] = resume  # {var:resume} = tableau recap de toutes les VMs
    msg = await send_notification_object(target, variables=variables, source="proxmox")
    if msg is None:
        raise HTTPException(500, "Echec d'envoi (voir logs)")
    return {"status": "sent", "slug": slug, "message_id": str(msg.id)}
