"""Serveur MCP intégré à BotPanel — sans dépendance externe.

Expose des « outils » à Claude (claude.ai / Claude Desktop) pour piloter BotPanel :
lister / déclencher / créer des notifications, envoyer un message ponctuel sur
Discord, lire l'état et l'historique.

Transport : MCP « Streamable HTTP » implémenté à la main (JSON-RPC 2.0 sur
POST /mcp). Les réponses sont renvoyées en **SSE** (`text/event-stream`) quand le
client l'accepte — ce qu'attendent la plupart des clients MCP, dont Claude — et
en `application/json` sinon. `GET /mcp` -> 405 (pas de flux serveur->client).

Sécurité : route MACHINE (hors login humain, cf. `_AUTH_PUBLIC_PREFIXES`),
protégée par la **clé API BotPanel** présentée en `Authorization: Bearer <clé>`
ou `X-API-Key: <clé>`.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.api.routes.system import INSTALL_DIR, _run as _sys_run
from app.config import settings
from app.db.models import Notification, NotificationButton, NotificationField, NotificationIn
from app.db.repositories import LogRepository, NotificationRepository
from app.integration import get_api_key

logger = logging.getLogger(__name__)
router = APIRouter()

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "BotPanel", "version": "1.0.0"}


# ======================================================================
#  Définition des outils (JSON Schema)
# ======================================================================
TOOLS = [
    {
        "name": "list_notifications",
        "description": "Liste toutes les notifications enregistrées dans BotPanel "
        "(slug, titre, groupe). Utile avant d'en déclencher une.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "send_notification",
        "description": "Déclenche l'envoi d'une notification BotPanel existante, "
        "par son slug. Variables optionnelles pour remplir les {var:nom}.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Slug de la notification à envoyer."},
                "variables": {
                    "type": "object",
                    "description": "Valeurs pour les {var:nom} (ex. {\"statut\":\"OK\"}).",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["slug"],
        },
    },
    {
        "name": "create_notification",
        "description": "Crée une nouvelle notification permanente dans BotPanel. "
        "Le slug doit être unique (minuscules, chiffres, underscore).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Identifiant unique (a-z0-9_)."},
                "title": {"type": "string", "description": "Titre de l'embed Discord."},
                "message": {"type": "string", "description": "Message (markdown Discord)."},
                "channel_id": {
                    "type": "string",
                    "description": "ID du salon Discord. Si omis, le salon par défaut est utilisé.",
                },
                "color": {"type": "string", "description": "Couleur hex, ex. \"#e8c547\"."},
                "footer": {"type": "string", "description": "Texte de pied de page (optionnel)."},
                "list_group": {"type": "string", "description": "Groupe de rangement sur le site (optionnel)."},
                "fields": {
                    "type": "array",
                    "description": "Champs en grille : liste d'objets {name, value}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["name", "value"],
                    },
                },
                "image_url": {"type": "string", "description": "Grande image affichée sous le texte (URL)."},
                "icon_url": {"type": "string", "description": "Petite image (miniature) en haut à droite (URL)."},
                "delete_button": {"type": "boolean", "description": "Ajoute le bouton intégré « Supprimer »."},
                "snooze_button": {"type": "boolean", "description": "Ajoute le bouton intégré « Snooze »."},
                "buttons": {
                    "type": "array",
                    "description": "Boutons d'action cliquables dans Discord. Chaque clic appelle un "
                    "service Home Assistant (ex. allumer une lumière, verrouiller une porte).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "Texte du bouton."},
                            "style": {
                                "type": "string",
                                "enum": ["primary", "secondary", "success", "danger"],
                                "description": "Couleur : primary=bleu, secondary=gris, success=vert, danger=rouge.",
                            },
                            "emoji": {"type": "string", "description": "Emoji optionnel sur le bouton."},
                            "ha_service": {"type": "string", "description": "Service HA appelé au clic, ex. light.turn_on, lock.lock, script.xxx."},
                            "ha_entity_id": {"type": "string", "description": "Entité ciblée, ex. light.salon (optionnel)."},
                            "ha_data": {"type": "object", "description": "Données additionnelles du service, ex. {\"brightness\": 255} (optionnel)."},
                        },
                        "required": ["label", "ha_service"],
                    },
                },
            },
            "required": ["slug", "title", "message"],
        },
    },
    {
        "name": "send_quick_message",
        "description": "Envoie un message ponctuel sur un salon Discord, SANS créer "
        "de notification permanente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "message": {"type": "string"},
                "channel_id": {
                    "type": "string",
                    "description": "ID du salon Discord. Si omis, le salon par défaut est utilisé.",
                },
                "color": {"type": "string", "description": "Couleur hex, ex. \"#e8c547\"."},
                "image_url": {"type": "string", "description": "Grande image sous le texte (URL, optionnel)."},
                "icon_url": {"type": "string", "description": "Miniature en haut à droite (URL, optionnel)."},
            },
            "required": ["title", "message"],
        },
    },
    {
        "name": "get_state",
        "description": "État de BotPanel : bot Discord en ligne, envois du jour / total, "
        "nombre de notifications, dernière alerte.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_history",
        "description": "Derniers envois (historique). Paramètre limit optionnel (défaut 20).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Nombre d'entrées (1-100).", "minimum": 1, "maximum": 100}
            },
        },
    },
    {
        "name": "check_update",
        "description": "Vérifie si une mise à jour du code BotPanel est disponible (git) : commit "
        "actuel, commit cible, et la liste des changements en attente. Lecture seule, sûr.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_site",
        "description": "Met à jour l'instance BotPanel : fait d'abord une SAUVEGARDE du code "
        "(point de rollback), puis applique la mise à jour (git) et redémarre le service. "
        "SÉCURITÉ : n'agit QUE si confirm vaut \"OUI\" ; sinon, renvoie un aperçu sans rien changer. "
        "Toujours demander l'accord de l'utilisateur avant de confirmer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {
                    "type": "string",
                    "description": "Mettre \"OUI\" pour appliquer réellement. Vide ou autre = simple aperçu (aucune modif).",
                }
            },
        },
    },
    {
        "name": "rollback_site",
        "description": "Revient à la dernière sauvegarde de code (avant la dernière mise à jour) "
        "et redémarre. SÉCURITÉ : n'agit QUE si confirm vaut \"OUI\".",
        "inputSchema": {
            "type": "object",
            "properties": {
                "confirm": {"type": "string", "description": "Mettre \"OUI\" pour appliquer le rollback. Sinon, aperçu."}
            },
        },
    },
    {
        "name": "delete_notification",
        "description": "Supprime définitivement une notification BotPanel (par son slug).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Slug de la notification à supprimer."}
            },
            "required": ["slug"],
        },
    },
    {
        "name": "update_notification",
        "description": "Modifie une notification existante (identifiée par son slug). Seuls les "
        "champs fournis sont changés ; les autres restent inchangés. Peut aussi la renommer (new_slug).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Slug de la notification à modifier."},
                "new_slug": {"type": "string", "description": "Nouveau slug si tu veux la renommer (a-z0-9_)."},
                "title": {"type": "string"},
                "message": {"type": "string"},
                "channel_id": {"type": "string"},
                "color": {"type": "string", "description": "Couleur hex, ex. \"#e8c547\"."},
                "footer": {"type": "string"},
                "list_group": {"type": "string"},
                "image_url": {"type": "string"},
                "icon_url": {"type": "string"},
                "delete_button": {"type": "boolean"},
                "snooze_button": {"type": "boolean"},
                "fields": {
                    "type": "array",
                    "description": "Remplace TOUS les champs par cette liste {name, value}.",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                        "required": ["name", "value"],
                    },
                },
                "buttons": {
                    "type": "array",
                    "description": "Remplace TOUS les boutons par cette liste (voir create_notification).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "style": {"type": "string", "enum": ["primary", "secondary", "success", "danger"]},
                            "emoji": {"type": "string"},
                            "ha_service": {"type": "string"},
                            "ha_entity_id": {"type": "string"},
                            "ha_data": {"type": "object"},
                        },
                        "required": ["label", "ha_service"],
                    },
                },
            },
            "required": ["slug"],
        },
    },
]


# ======================================================================
#  Helpers
# ======================================================================
def _parse_color(c, default: int = 0xFFFF00) -> int:
    if c is None:
        return default
    if isinstance(c, int):
        return c
    s = str(c).strip().lstrip("#")
    try:
        return int(s, 16)
    except ValueError:
        return default


def _default_channel() -> str:
    return str(settings.discord_default_channel_id or "")


# ======================================================================
#  Implémentations des outils (renvoient un texte lisible)
# ======================================================================
async def _tool_list_notifications(args: dict) -> str:
    notifs = await NotificationRepository().list_all()
    if not notifs:
        return "Aucune notification enregistrée."
    lines = [
        f"- {n.slug} — « {n.title} »" + (f"  [{n.list_group}]" if n.list_group else "")
        for n in notifs
    ]
    return f"{len(notifs)} notification(s) :\n" + "\n".join(lines)


async def _tool_send_notification(args: dict) -> str:
    from app.bot.notifications import send_notification

    slug = (args.get("slug") or "").strip()
    if not slug:
        raise ValueError("Le paramètre 'slug' est requis.")
    variables = args.get("variables") or None
    msg = await send_notification(slug, variables=variables, source="mcp")
    if msg is None:
        raise RuntimeError(
            f"Échec de l'envoi de '{slug}' (slug introuvable, salon injoignable ou bot hors ligne)."
        )
    return f"✅ Notification '{slug}' envoyée (message Discord {msg.id})."


async def _tool_create_notification(args: dict) -> str:
    repo = NotificationRepository()
    slug = (args.get("slug") or "").strip()
    if await repo.get_by_slug(slug) is not None:
        raise ValueError(f"Le slug '{slug}' existe déjà.")
    fields = [
        NotificationField(name=f.get("name", ""), value_template=f.get("value", ""), position=i)
        for i, f in enumerate(args.get("fields") or [])
    ]
    buttons = []
    for i, b in enumerate(args.get("buttons") or []):
        data = b.get("ha_data")
        buttons.append(
            NotificationButton(
                label=b.get("label", ""),
                style=b.get("style") or "primary",
                emoji=b.get("emoji") or None,
                ha_service=b.get("ha_service", ""),
                ha_entity_id=b.get("ha_entity_id") or None,
                ha_data_json=(json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else None),
                position=i,
            )
        )
    payload = NotificationIn(
        slug=slug,
        channel_id=(args.get("channel_id") or _default_channel()),
        title=args.get("title", ""),
        message=args.get("message", ""),
        color=_parse_color(args.get("color")),
        footer=args.get("footer") or None,
        list_group=args.get("list_group") or None,
        icon_url=args.get("icon_url") or None,
        image_url=args.get("image_url") or None,
        delete_button=bool(args.get("delete_button")),
        snooze_button=bool(args.get("snooze_button")),
        fields=fields,
        buttons=buttons,
    )
    notif = await repo.create(payload)
    extra = []
    if buttons:
        extra.append(f"{len(buttons)} bouton(s)")
    if fields:
        extra.append(f"{len(fields)} champ(s)")
    suffix = (" — " + ", ".join(extra)) if extra else ""
    return f"✅ Notification créée : slug '{notif.slug}' (id {notif.id}){suffix}. Déclenche-la avec send_notification."


async def _tool_send_quick_message(args: dict) -> str:
    from app.bot.notifications import send_notification_object

    channel_id = (args.get("channel_id") or _default_channel()).strip()
    if not channel_id:
        raise ValueError("Aucun salon : fournis 'channel_id' ou configure un salon par défaut.")
    notif = Notification(
        id=0,
        slug="_mcp_quick",
        channel_id=channel_id,
        title=args.get("title", ""),
        message=args.get("message", ""),
        color=_parse_color(args.get("color"), default=0xE8C547),
        icon_url=args.get("icon_url") or None,
        image_url=args.get("image_url") or None,
        show_timestamp=True,
    )
    msg = await send_notification_object(notif, source="mcp")
    if msg is None:
        raise RuntimeError("Échec de l'envoi (salon injoignable ou bot hors ligne).")
    return f"✅ Message envoyé sur le salon {channel_id} (message Discord {msg.id})."


async def _tool_get_state(args: dict) -> str:
    try:
        from app.bot.client import bot
        online = bool(bot.is_ready())
    except Exception:  # noqa: BLE001
        online = False
    log_repo = LogRepository()
    today = await log_repo.stats_today()
    total = await log_repo.count_sends_total()
    last = await log_repo.last_send()
    count = await NotificationRepository().count_all()
    last_txt = (
        f"{last.get('slug')} ({last.get('source')}) le {last.get('created_at')}"
        if last else "aucune"
    )
    return (
        f"Bot Discord : {'🟢 en ligne' if online else '🔴 hors ligne'}\n"
        f"Envois aujourd'hui : {today.get('sent_ok', 0)}\n"
        f"Envois au total : {total}\n"
        f"Notifications configurées : {count}\n"
        f"Dernière alerte : {last_txt}"
    )


async def _tool_list_history(args: dict) -> str:
    limit = int(args.get("limit") or 20)
    limit = max(1, min(100, limit))
    logs = await LogRepository().list_recent(limit=limit, kind="send")
    if not logs:
        return "Aucun envoi dans l'historique."
    lines = [
        f"{'✅' if l.success else '❌'} {l.created_at} · {l.notification_slug or '—'} "
        f"· {l.source or '—'}" + (f" · {l.detail}" if l.detail else "")
        for l in logs
    ]
    return f"{len(logs)} dernier(s) envoi(s) :\n" + "\n".join(lines)


def _fields_from_args(raw) -> list:
    return [
        NotificationField(name=f.get("name", ""), value_template=f.get("value", ""), position=i)
        for i, f in enumerate(raw or [])
    ]


def _buttons_from_args(raw) -> list:
    out = []
    for i, b in enumerate(raw or []):
        data = b.get("ha_data")
        out.append(
            NotificationButton(
                label=b.get("label", ""),
                style=b.get("style") or "primary",
                emoji=b.get("emoji") or None,
                ha_service=b.get("ha_service", ""),
                ha_entity_id=b.get("ha_entity_id") or None,
                ha_data_json=(json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else None),
                position=i,
            )
        )
    return out


async def _tool_delete_notification(args: dict) -> str:
    repo = NotificationRepository()
    slug = (args.get("slug") or "").strip()
    existing = await repo.get_by_slug(slug)
    if existing is None:
        raise ValueError(f"Notification '{slug}' introuvable.")
    if not await repo.delete(existing.id):
        raise RuntimeError("Suppression échouée.")
    return f"🗑️ Notification '{slug}' supprimée."


async def _tool_update_notification(args: dict) -> str:
    repo = NotificationRepository()
    slug = (args.get("slug") or "").strip()
    existing = await repo.get_by_slug(slug)
    if existing is None:
        raise ValueError(f"Notification '{slug}' introuvable.")
    data = existing.model_dump()
    data.pop("id", None)
    # On n'écrase que les champs fournis.
    if "title" in args:
        data["title"] = args["title"]
    if "message" in args:
        data["message"] = args["message"]
    if args.get("channel_id"):
        data["channel_id"] = args["channel_id"]
    if args.get("color") is not None and "color" in args:
        data["color"] = _parse_color(args["color"], default=data.get("color", 0xFFFF00))
    if "footer" in args:
        data["footer"] = args["footer"] or None
    if "list_group" in args:
        data["list_group"] = args["list_group"] or None
    if "image_url" in args:
        data["image_url"] = args["image_url"] or None
    if "icon_url" in args:
        data["icon_url"] = args["icon_url"] or None
    if "delete_button" in args:
        data["delete_button"] = bool(args["delete_button"])
    if "snooze_button" in args:
        data["snooze_button"] = bool(args["snooze_button"])
    if "fields" in args:
        data["fields"] = _fields_from_args(args["fields"])
    if "buttons" in args:
        data["buttons"] = _buttons_from_args(args["buttons"])
    renamed = False
    if args.get("new_slug"):
        new_slug = args["new_slug"].strip()
        if new_slug != slug:
            if await repo.get_by_slug(new_slug) is not None:
                raise ValueError(f"Le slug '{new_slug}' existe déjà.")
            data["slug"] = new_slug
            renamed = True
    payload = NotificationIn(**data)
    if await repo.update(existing.id, payload) is None:
        raise RuntimeError("Mise à jour échouée.")
    suffix = f" (renommée '{payload.slug}')" if renamed else ""
    return f"✅ Notification '{slug}' mise à jour{suffix}."


HANDLERS = {
    "list_notifications": _tool_list_notifications,
    "send_notification": _tool_send_notification,
    "create_notification": _tool_create_notification,
    "update_notification": _tool_update_notification,
    "delete_notification": _tool_delete_notification,
    "send_quick_message": _tool_send_quick_message,
    "get_state": _tool_get_state,
    "list_history": _tool_list_history,
    "check_update": None,     # défini plus bas (après les helpers git)
    "update_site": None,
    "rollback_site": None,
}


# ======================================================================
#  Mise à jour / rollback du code (git) — avec sauvegarde + confirmation
# ======================================================================
_BACKUP_TAG = "botpanel-pre-update"


async def _git(*args: str, timeout: float = 60.0) -> dict:
    return await _sys_run(["git", *args], cwd=INSTALL_DIR, timeout=timeout)


def _confirmed(args: dict) -> bool:
    return str(args.get("confirm", "")).strip().upper() in ("OUI", "YES", "TRUE", "CONFIRM", "OK")


def _schedule_restart() -> None:
    """Quitte le process après la réponse -> systemd (Restart=on-failure) relance."""
    async def _exit() -> None:
        await asyncio.sleep(0.6)
        os._exit(1)  # noqa: SLF001
    asyncio.create_task(_exit())


async def _tool_check_update(args: dict) -> str:
    if not (INSTALL_DIR / ".git").exists():
        raise RuntimeError(f"{INSTALL_DIR} n'est pas un dépôt git.")
    branch = (await _git("rev-parse", "--abbrev-ref", "HEAD", timeout=5))["stdout"].strip() or "main"
    await _git("fetch", "--prune", timeout=120)
    cur = (await _git("rev-parse", "--short", "HEAD", timeout=5))["stdout"].strip()
    remote = (await _git("rev-parse", "--short", f"origin/{branch}", timeout=5))["stdout"].strip()
    log = (await _git("log", "--oneline", f"HEAD..origin/{branch}", timeout=10))["stdout"].strip()
    if not log or cur == remote:
        return f"✅ À jour (commit {cur}, branche {branch}). Aucune mise à jour en attente."
    n = len(log.splitlines())
    return (
        f"⬆️ Mise à jour disponible — {n} changement(s) :\n{log}\n\n"
        f"Actuel {cur} → cible {remote} (branche {branch}).\n"
        f"Pour l'appliquer : update_site(confirm=\"OUI\") — sauvegarde puis MàJ + redémarrage."
    )


async def _tool_update_site(args: dict) -> str:
    if not (INSTALL_DIR / ".git").exists():
        raise RuntimeError(f"{INSTALL_DIR} n'est pas un dépôt git.")
    if not _confirmed(args):
        preview = await _tool_check_update(args)
        return (
            "⚠️ Confirmation requise — je ne mets RIEN à jour sans ton accord.\n\n"
            + preview
            + "\n\nQuand tu es d'accord, relance avec confirm=\"OUI\"."
        )
    branch = (await _git("rev-parse", "--abbrev-ref", "HEAD", timeout=5))["stdout"].strip() or "main"
    before = (await _git("rev-parse", "HEAD", timeout=5))["stdout"].strip()
    before_short = before[:7]
    # 1) SAUVEGARDE du code : tag de rollback sur l'état actuel
    await _git("tag", "-f", _BACKUP_TAG, before, timeout=10)
    # 2) récupération + application
    fetch = await _git("fetch", "--prune", timeout=120)
    if fetch["exit_code"] != 0:
        raise RuntimeError(f"git fetch a échoué : {fetch['stderr'].strip()}")
    reset = await _git("reset", "--hard", f"origin/{branch}", timeout=60)
    if reset["exit_code"] != 0:
        raise RuntimeError(f"git reset a échoué : {reset['stderr'].strip()}")
    after = (await _git("rev-parse", "--short", "HEAD", timeout=5))["stdout"].strip()
    # 3) dépendances Python si un venv existe
    venv_pip = INSTALL_DIR / ".venv" / "bin" / "pip"
    if venv_pip.exists():
        await _sys_run(
            [str(venv_pip), "install", "-q", "-r", str(INSTALL_DIR / "requirements.txt")],
            cwd=INSTALL_DIR, timeout=180,
        )
    # 4) redémarrage
    _schedule_restart()
    return (
        f"✅ Mis à jour : {before_short} → {after} (branche {branch}).\n"
        f"💾 Sauvegarde du code faite (tag '{_BACKUP_TAG}' sur {before_short}) — rollback possible.\n"
        f"🔄 Redémarrage en cours… reconnecte le connecteur dans ~10 s."
    )


async def _tool_rollback_site(args: dict) -> str:
    if not (INSTALL_DIR / ".git").exists():
        raise RuntimeError(f"{INSTALL_DIR} n'est pas un dépôt git.")
    tag = await _git("rev-parse", "--short", _BACKUP_TAG, timeout=5)
    if tag["exit_code"] != 0:
        raise RuntimeError(f"Aucune sauvegarde trouvée (tag '{_BACKUP_TAG}' absent).")
    target = tag["stdout"].strip()
    cur = (await _git("rev-parse", "--short", "HEAD", timeout=5))["stdout"].strip()
    if not _confirmed(args):
        return (
            f"⚠️ Confirmation requise — rollback {cur} → {target} (dernière sauvegarde).\n"
            f"Relance avec confirm=\"OUI\" pour revenir en arrière + redémarrer."
        )
    reset = await _git("reset", "--hard", _BACKUP_TAG, timeout=60)
    if reset["exit_code"] != 0:
        raise RuntimeError(f"rollback a échoué : {reset['stderr'].strip()}")
    after = (await _git("rev-parse", "--short", "HEAD", timeout=5))["stdout"].strip()
    _schedule_restart()
    return f"↩️ Rollback effectué : {cur} → {after}. 🔄 Redémarrage en cours…"


HANDLERS["check_update"] = _tool_check_update
HANDLERS["update_site"] = _tool_update_site
HANDLERS["rollback_site"] = _tool_rollback_site


# ======================================================================
#  Auth (clé API BotPanel : Bearer, X-API-Key, ou jeton dans l'URL)
# ======================================================================
async def _authorized(request: Request, path_token: str | None = None) -> bool:
    stored = await get_api_key()
    if not stored:
        return False
    # 1) en-tête Authorization: Bearer <clé>
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    # 2) en-tête X-API-Key
    if not token:
        token = (request.headers.get("x-api-key") or "").strip()
    # 3) jeton dans l'URL (/mcp/<clé>) — pratique pour les connecteurs sans en-tête
    if not token and path_token:
        token = path_token.strip()
    return bool(token) and hmac.compare_digest(stored, token)


# ======================================================================
#  Dispatch JSON-RPC 2.0
# ======================================================================
class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def _dispatch(method: str, params: dict):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            raise _RpcError(-32602, f"Outil inconnu : {name}")
        try:
            text = await handler(args)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:  # noqa: BLE001 — erreur d'outil = isError, pas erreur JSON-RPC
            logger.warning("Outil MCP '%s' a échoué : %s", name, exc)
            return {"content": [{"type": "text", "text": f"Erreur : {exc}"}], "isError": True}
    if method == "ping":
        return {}
    raise _RpcError(-32601, f"Méthode inconnue : {method}")


async def _handle_one(msg: dict):
    """Traite un message JSON-RPC. Renvoie la réponse, ou None pour une notification."""
    req_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params") or {}
    if req_id is None:
        # Notification (ex. notifications/initialized) : rien à renvoyer.
        return None
    try:
        result = await _dispatch(method, params)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except _RpcError as err:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": err.code, "message": err.message}}


def _wants_sse(request: Request) -> bool:
    return "text/event-stream" in (request.headers.get("accept") or "").lower()


def _respond(payload, headers: dict, sse: bool):
    """Renvoie la réponse en SSE (text/event-stream) si le client l'accepte, sinon JSON.

    La plupart des clients MCP « Streamable HTTP » (dont Claude) attendent du SSE :
    un seul évènement `message` contenant la réponse JSON-RPC, puis fermeture.
    """
    if not sse:
        return JSONResponse(payload, headers=headers)
    data = json.dumps(payload, ensure_ascii=False)

    async def _gen():
        yield f"event: message\ndata: {data}\n\n"

    h = dict(headers)
    h["Cache-Control"] = "no-cache"
    return StreamingResponse(_gen(), media_type="text/event-stream", headers=h)


@router.post("/mcp")
@router.post("/mcp/")
async def mcp_endpoint(request: Request):
    return await _serve(request, None)


@router.post("/mcp/{token}")
async def mcp_endpoint_token(token: str, request: Request):
    # Variante avec la clé dans l'URL (connecteurs sans en-tête custom).
    return await _serve(request, token)


async def _serve(request: Request, path_token: str | None):
    if not await _authorized(request, path_token):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32001, "message": "Clé API invalide ou absente."}},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON invalide."}},
            status_code=400,
        )

    headers = {}
    # Session MCP : on en assigne une à l'initialize (non contraignante côté serveur).
    if isinstance(body, dict) and body.get("method") == "initialize":
        headers["Mcp-Session-Id"] = uuid.uuid4().hex
    sse = _wants_sse(request)

    if isinstance(body, list):  # batch
        responses = [r for r in [await _handle_one(m) for m in body] if r is not None]
        if not responses:
            return Response(status_code=202, headers=headers)
        return _respond(responses, headers, sse)

    response = await _handle_one(body)
    if response is None:  # notification -> 202 sans corps
        return Response(status_code=202, headers=headers)
    return _respond(response, headers, sse)


@router.get("/mcp")
@router.get("/mcp/{token}")
async def mcp_get(token: str | None = None) -> Response:
    # Pas de flux SSE serveur -> méthode non autorisée (conforme au spec).
    return Response(status_code=405, headers={"Allow": "POST"})


@router.delete("/mcp")
@router.delete("/mcp/{token}")
async def mcp_delete(token: str | None = None) -> Response:
    # Fin de session : rien à nettoyer (serveur sans état).
    return Response(status_code=200)
