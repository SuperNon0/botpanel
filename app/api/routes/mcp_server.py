"""Serveur MCP intégré à BotPanel — sans dépendance externe.

Expose des « outils » à Claude (claude.ai / Claude Desktop) pour piloter BotPanel :
gérer les notifications, les commandes slash, les blocs de monitoring et les
couleurs préconfigurées, envoyer
un message ponctuel sur Discord, lire l'état, l'historique et les erreurs.

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
from app.db.models import (
    ChannelPreset,
    ColorPreset,
    HaButton,
    MonitoringBlockIn,
    Notification,
    NotificationButton,
    NotificationField,
    NotificationIn,
    SlashCommandIn,
)
from app.db.repositories import (
    LogRepository,
    MonitoringRepository,
    NotificationRepository,
    SettingsRepository,
    SlashCommandRepository,
    ThreadRepository,
)
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
        "description": "Historique BotPanel (envois, commandes, monitoring, clics…), du plus récent "
        "au plus ancien. Filtre optionnel par type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Nombre d'entrées (1-100, défaut 20).", "minimum": 1, "maximum": 100},
                "kind": {
                    "type": "string",
                    "enum": ["all", "send", "command", "monitoring", "button", "snooze", "delete"],
                    "description": "Type d'entrée : send=envoi de notification, command=commande slash, "
                    "monitoring=mise à jour d'un bloc, button/snooze/delete=clics. Défaut : all.",
                },
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
    kind = (args.get("kind") or "all").strip()
    logs = await LogRepository().list_recent(limit=limit, kind=None if kind == "all" else kind)
    if not logs:
        return "Rien dans l'historique."
    return f"{len(logs)} dernière(s) entrée(s) :\n" + "\n".join(_log_line(l) for l in logs)


def _log_line(l) -> str:
    who = f" · par {l.user_name}" if l.user_name else ""
    btn = f" · bouton « {l.button_label} »" if l.button_label else ""
    return (
        f"{'✅' if l.success else '❌'} {l.created_at} · {l.kind} · {l.notification_slug or '—'} "
        f"· {l.source or '—'}{who}{btn}" + (f" · {l.detail}" if l.detail else "")
    )


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
#  Commandes slash, blocs de monitoring, erreurs, couleurs
# ======================================================================
_HA_BUTTONS_SCHEMA = {
    "type": "array",
    "description": "Boutons d'action sous le message. Chaque clic appelle un service Home Assistant.",
    "items": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Texte du bouton."},
            "style": {"type": "string", "enum": ["primary", "secondary", "success", "danger"]},
            "emoji": {"type": "string"},
            "ha_service": {"type": "string", "description": "Service HA, ex. light.toggle."},
            "ha_entity_id": {"type": "string", "description": "Entité ciblée (optionnel)."},
            "ha_data": {"type": "object", "description": "Données du service (optionnel)."},
        },
        "required": ["label", "ha_service"],
    },
}

_COMMAND_PROPS = {
    "description": {"type": "string", "description": "Description affichée dans Discord (100 car. max)."},
    "action_type": {
        "type": "string",
        "enum": ["message", "service", "script", "scene", "notification"],
        "description": "message=répond seulement ; service=appelle ha_service ; script/scene=lance "
        "ha_entity_id (script.xxx / scene.xxx) ; notification=envoie notification_slug.",
    },
    "ha_service": {"type": "string", "description": "Service HA pour action_type=service, ex. light.toggle."},
    "ha_entity_id": {"type": "string", "description": "Entité ciblée (ou script.xxx / scene.xxx)."},
    "ha_data": {"type": "object", "description": "Données du service HA, ex. {\"brightness\": 255}."},
    "notification_slug": {"type": "string", "description": "Notification envoyée pour action_type=notification."},
    "response_message": {
        "type": "string",
        "description": "Réponse affichée. Accepte {state:sensor.x}, {attr:entité:attribut} et le Jinja HA.",
    },
    "response_ephemeral": {"type": "boolean", "description": "Réponse visible seulement par l'auteur (défaut true)."},
    "response_embed": {"type": "boolean", "description": "Réponse en encadré (titre, couleur, image)."},
    "response_title": {"type": "string", "description": "Titre de l'encadré."},
    "response_color": {"type": "string", "description": "Couleur hex de l'encadré, ex. \"#e8c547\"."},
    "response_image_url": {"type": "string", "description": "Image de l'encadré (URL)."},
    "buttons": _HA_BUTTONS_SCHEMA,
    "list_group": {"type": "string", "description": "Groupe de rangement sur le site."},
    "enabled": {"type": "boolean", "description": "Commande active sur Discord (défaut true)."},
}

_MONITORING_PROPS = {
    "name": {"type": "string", "description": "Titre du bloc (placeholders HA acceptés)."},
    "icon": {"type": "string", "description": "Emoji devant le titre, ou URL d'une miniature."},
    "color": {"type": "string", "description": "Couleur hex, ex. \"#49a0df\"."},
    "enabled": {
        "type": "boolean",
        "description": "Actif = le message Discord est posté puis mis à jour en boucle. Défaut false.",
    },
    "channel_id": {"type": "string", "description": "Salon Discord. Si omis, le salon de monitoring par défaut."},
    "interval_seconds": {"type": "integer", "minimum": 30, "description": "Fréquence de mise à jour (défaut 300)."},
    "footer": {"type": "string", "description": "Pied de page."},
    "list_group": {"type": "string", "description": "Groupe de rangement sur le site."},
    "description": {"type": "string", "description": "Texte sous le titre ({state:...} / Jinja acceptés)."},
    "thumbnail_url": {"type": "string", "description": "Miniature en haut à droite (URL)."},
    "image_url": {"type": "string", "description": "Grande image (URL)."},
    "show_timestamp": {"type": "boolean", "description": "Heure de mise à jour dans le pied (défaut true)."},
    "refresh_button": {"type": "boolean", "description": "Ajoute un bouton « Actualiser »."},
    "fields": {
        "type": "array",
        "description": "Valeurs affichées en grille.",
        "items": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "icon": {"type": "string", "description": "Emoji devant le libellé."},
                "entity_id": {"type": "string", "description": "Entité HA lue, ex. sensor.temp_salon."},
                "attribute": {"type": "string", "description": "Attribut à lire au lieu de l'état."},
                "suffix": {"type": "string", "description": "Unité affichée (vide = unité HA)."},
                "decimals": {"type": "integer", "description": "Arrondi des nombres."},
                "value_template": {"type": "string", "description": "Texte/Jinja libre (remplace entity_id)."},
                "inline": {"type": "boolean"},
            },
        },
    },
    "buttons": _HA_BUTTONS_SCHEMA,
}

# Clés de config_json pilotées par les outils monitoring.
_MONITORING_CFG_KEYS = (
    "description", "thumbnail_url", "image_url", "show_timestamp", "refresh_button", "fields",
)

TOOLS.extend([
    {
        "name": "list_commands",
        "description": "Liste les commandes slash Discord de BotPanel (nom, action, état).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_command",
        "description": "Détail complet d'une commande slash (par son nom), utile avant de la modifier.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Nom de la commande, sans « / »."}},
            "required": ["name"],
        },
    },
    {
        "name": "create_command",
        "description": "Crée une commande slash Discord (ex. /garage). Nom en minuscules, chiffres, - ou _ "
        "(32 car. max). Elle est synchronisée tout de suite sur Discord.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom sans « / » (a-z0-9_-)."},
                **_COMMAND_PROPS,
            },
            "required": ["name", "description", "action_type"],
        },
    },
    {
        "name": "update_command",
        "description": "Modifie une commande slash (par son nom). Seuls les champs fournis changent ; "
        "buttons remplace tous les boutons. new_name pour la renommer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom actuel de la commande."},
                "new_name": {"type": "string", "description": "Nouveau nom (optionnel)."},
                **_COMMAND_PROPS,
            },
            "required": ["name"],
        },
    },
    {
        "name": "delete_command",
        "description": "Supprime définitivement une commande slash (par son nom).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "run_command",
        "description": "Exécute une commande slash comme si on la tapait sur Discord (lance son action HA "
        "ou sa notification) et renvoie la réponse qu'elle afficherait.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_monitoring",
        "description": "Liste les blocs de monitoring (id, nom, actif, salon, fréquence).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_monitoring",
        "description": "Détail d'un bloc de monitoring (par id) + rendu actuel avec les vraies valeurs HA.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    {
        "name": "create_monitoring",
        "description": "Crée un bloc de monitoring : un message Discord mis à jour en boucle avec des "
        "valeurs Home Assistant. Créé inactif sauf si enabled=true.",
        "inputSchema": {
            "type": "object",
            "properties": _MONITORING_PROPS,
            "required": ["name"],
        },
    },
    {
        "name": "update_monitoring",
        "description": "Modifie un bloc de monitoring (par id). Seuls les champs fournis changent ; "
        "fields et buttons remplacent toute la liste.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, **_MONITORING_PROPS},
            "required": ["id"],
        },
    },
    {
        "name": "delete_monitoring",
        "description": "Supprime définitivement un bloc de monitoring (par id).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    {
        "name": "send_monitoring",
        "description": "Envoie / met à jour tout de suite le message Discord d'un bloc de monitoring actif.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
    {
        "name": "list_errors",
        "description": "Erreurs récentes : entrées en échec de l'historique + derniers avertissements "
        "et erreurs du serveur (gardés en mémoire depuis le dernier redémarrage).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Défaut 20."}
            },
        },
    },
    {
        "name": "list_colors",
        "description": "Liste les couleurs préconfigurées (nom + hex) proposées dans les éditeurs du site.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_color",
        "description": "Crée une couleur préconfigurée, ou la modifie si le nom existe déjà. "
        "new_name pour la renommer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom de la couleur (64 car. max)."},
                "color": {"type": "string", "description": "Couleur hex, ex. \"#e8c547\"."},
                "new_name": {"type": "string", "description": "Nouveau nom (optionnel)."},
            },
            "required": ["name", "color"],
        },
    },
    {
        "name": "delete_color",
        "description": "Supprime une couleur préconfigurée (par son nom).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
])


def _ha_buttons_from_args(raw) -> list[HaButton]:
    out = []
    for b in raw or []:
        data = b.get("ha_data")
        out.append(
            HaButton(
                label=b.get("label", ""),
                style=b.get("style") or "primary",
                emoji=b.get("emoji") or None,
                ha_service=b.get("ha_service", ""),
                ha_entity_id=b.get("ha_entity_id") or None,
                ha_data_json=(json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else None),
            )
        )
    return out


def _apply_command_args(data: dict, args: dict) -> None:
    """Reporte dans `data` (forme SlashCommandIn) les champs fournis par Claude."""
    for key in ("description", "action_type", "response_message"):
        if key in args:
            data[key] = args[key]
    for key in ("ha_service", "ha_entity_id", "notification_slug", "response_title",
                "response_image_url", "list_group"):
        if key in args:
            data[key] = args[key] or None
    for key in ("response_ephemeral", "response_embed", "enabled"):
        if key in args:
            data[key] = bool(args[key])
    if "ha_data" in args:
        d = args["ha_data"]
        data["ha_data_json"] = json.dumps(d, ensure_ascii=False) if isinstance(d, dict) and d else None
    if args.get("response_color"):
        data["response_color"] = _parse_color(args["response_color"], default=data.get("response_color", 0xE8C547))
    if "buttons" in args:
        data["buttons"] = _ha_buttons_from_args(args["buttons"])


async def _check_command_name(repo: SlashCommandRepository, name: str, cmd_id: int | None = None) -> None:
    from app.bot.slash_sync import RESERVED_NAMES

    if name in RESERVED_NAMES:
        raise ValueError(f"/{name} est une commande fixe de BotPanel (nom réservé).")
    other = await repo.get_by_name(name)
    if other is not None and other.id != cmd_id:
        raise ValueError(f"/{name} existe déjà.")


async def _get_command(repo: SlashCommandRepository, args: dict):
    name = (args.get("name") or "").strip().lstrip("/")
    cmd = await repo.get_by_name(name)
    if cmd is None:
        raise ValueError(f"Commande /{name} introuvable.")
    return cmd


async def _tool_list_commands(args: dict) -> str:
    cmds = await SlashCommandRepository().list_all()
    if not cmds:
        return "Aucune commande slash."
    lines = []
    for c in cmds:
        target = c.ha_service or c.ha_entity_id or c.notification_slug or ""
        lines.append(
            f"- /{c.name} — {c.description} · {c.action_type}"
            + (f" ({target})" if target else "")
            + ("" if c.enabled else " · désactivée")
            + (f"  [{c.list_group}]" if c.list_group else "")
        )
    return f"{len(cmds)} commande(s) :\n" + "\n".join(lines)


async def _tool_get_command(args: dict) -> str:
    cmd = await _get_command(SlashCommandRepository(), args)
    data = cmd.model_dump()
    data["response_color"] = f"#{cmd.response_color:06x}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _tool_create_command(args: dict) -> str:
    from app.api.routes.slash_commands import _resync_discord
    from app.db.repositories.slash_commands import MAX_SLASH_COMMANDS

    repo = SlashCommandRepository()
    name = (args.get("name") or "").strip().lstrip("/")
    if await repo.count() >= MAX_SLASH_COMMANDS:
        raise ValueError(f"Limite Discord atteinte ({MAX_SLASH_COMMANDS} commandes max).")
    await _check_command_name(repo, name)
    data: dict = {"name": name}
    _apply_command_args(data, args)
    cmd = await repo.create(SlashCommandIn(**data))
    await _resync_discord()
    return f"✅ Commande /{cmd.name} créée (id {cmd.id}). Teste-la avec run_command."


async def _tool_update_command(args: dict) -> str:
    from app.api.routes.slash_commands import _resync_discord

    repo = SlashCommandRepository()
    cmd = await _get_command(repo, args)
    data = cmd.model_dump(exclude={"id"})
    _apply_command_args(data, args)
    new_name = (args.get("new_name") or "").strip().lstrip("/")
    if new_name and new_name != cmd.name:
        await _check_command_name(repo, new_name, cmd.id)
        data["name"] = new_name
    payload = SlashCommandIn(**data)
    if await repo.update(cmd.id, payload) is None:
        raise RuntimeError("Mise à jour échouée.")
    await _resync_discord()
    suffix = f" (renommée /{payload.name})" if payload.name != cmd.name else ""
    return f"✅ Commande /{cmd.name} mise à jour{suffix}."


async def _tool_delete_command(args: dict) -> str:
    from app.api.routes.slash_commands import _resync_discord

    repo = SlashCommandRepository()
    cmd = await _get_command(repo, args)
    if not await repo.delete(cmd.id):
        raise RuntimeError("Suppression échouée.")
    await _resync_discord()
    return f"🗑️ Commande /{cmd.name} supprimée."


async def _tool_run_command(args: dict) -> str:
    from app.bot.slash_sync import _execute_action, render_command_response

    cmd = await _get_command(SlashCommandRepository(), args)
    log_repo = LogRepository()
    try:
        await _execute_action(cmd)
    except Exception as exc:  # noqa: BLE001
        await log_repo.add(kind="command", notification_slug=f"/{cmd.name}",
                           detail=str(exc)[:300], source="mcp", success=False)
        raise RuntimeError(f"Action de /{cmd.name} échouée : {exc}") from exc
    await log_repo.add(kind="command", notification_slug=f"/{cmd.name}",
                       detail=cmd.action_type, source="mcp", success=True)
    data = await render_command_response(cmd)
    parts = [f"✅ /{cmd.name} exécutée ({cmd.action_type})."]
    if data.get("title"):
        parts.append(f"Titre : {data['title']}")
    if data.get("message"):
        parts.append(f"Réponse : {data['message']}")
    return "\n".join(parts)


def _apply_monitoring_args(data: dict, args: dict) -> None:
    """Reporte dans `data` (forme MonitoringBlockIn) les champs fournis par Claude."""
    for key in ("name", "interval_seconds"):
        if key in args:
            data[key] = args[key]
    for key in ("icon", "footer", "list_group", "channel_id"):
        if key in args:
            data[key] = args[key] or None
    if "enabled" in args:
        data["enabled"] = bool(args["enabled"])
    if args.get("color"):
        data["color"] = _parse_color(args["color"], default=data.get("color", 0x49A0DF))
    try:
        cfg = json.loads(data.get("config_json") or "{}")
    except json.JSONDecodeError:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    for key in _MONITORING_CFG_KEYS:
        if key in args:
            cfg[key] = args[key]
    if "buttons" in args:
        cfg["buttons"] = [b.model_dump() for b in _ha_buttons_from_args(args["buttons"])]
    data["config_json"] = json.dumps(cfg, ensure_ascii=False)


async def _get_block(repo: MonitoringRepository, args: dict):
    try:
        block_id = int(args.get("id"))
    except (TypeError, ValueError):
        raise ValueError("Le paramètre 'id' (entier) est requis — voir list_monitoring.") from None
    block = await repo.get_by_id(block_id)
    if block is None:
        raise ValueError(f"Bloc de monitoring {block_id} introuvable.")
    return block


async def _tool_list_monitoring(args: dict) -> str:
    blocks = await MonitoringRepository().list_all()
    if not blocks:
        return "Aucun bloc de monitoring."
    lines = [
        f"- id {b.id} · « {b.name} » · {'🟢 actif' if b.enabled else '⚪ inactif'} "
        f"· salon {b.channel_id or 'monitoring par défaut'} · toutes les {b.interval_seconds} s"
        + (f"  [{b.list_group}]" if b.list_group else "")
        for b in blocks
    ]
    return f"{len(blocks)} bloc(s) :\n" + "\n".join(lines)


async def _tool_get_monitoring(args: dict) -> str:
    from app.bot.monitoring import block_config, render_block

    block = await _get_block(MonitoringRepository(), args)
    data = block.model_dump(exclude={"config_json"})
    data["color"] = f"#{block.color:06x}"
    data["config"] = block_config(block)
    try:
        rendered = await render_block(block)
    except Exception as exc:  # noqa: BLE001
        rendered = f"(rendu impossible : {exc})"
    return (
        "Configuration :\n" + json.dumps(data, ensure_ascii=False, indent=2)
        + "\n\nRendu actuel :\n" + json.dumps(rendered, ensure_ascii=False, indent=2)
    )


async def _tool_create_monitoring(args: dict) -> str:
    from app.api.routes.monitoring import _refresh_task

    data: dict = {}
    _apply_monitoring_args(data, args)
    block = await MonitoringRepository().create(MonitoringBlockIn(**data))
    await _refresh_task(block.id)
    state = "actif, il va être posté sur Discord" if block.enabled else \
        "inactif (active-le avec update_monitoring enabled=true)"
    return f"✅ Bloc « {block.name} » créé (id {block.id}), {state}."


async def _tool_update_monitoring(args: dict) -> str:
    from app.api.routes.monitoring import _refresh_task

    repo = MonitoringRepository()
    block = await _get_block(repo, args)
    data = block.model_dump(exclude={"id", "message_id"})
    _apply_monitoring_args(data, args)
    if await repo.update(block.id, MonitoringBlockIn(**data)) is None:
        raise RuntimeError("Mise à jour échouée.")
    await _refresh_task(block.id)
    return f"✅ Bloc {block.id} (« {data['name']} ») mis à jour."


async def _tool_delete_monitoring(args: dict) -> str:
    repo = MonitoringRepository()
    block = await _get_block(repo, args)
    try:
        from app.bot.monitoring import stop_block_task
        await stop_block_task(block.id)
    except Exception:  # noqa: BLE001
        pass
    if not await repo.delete(block.id):
        raise RuntimeError("Suppression échouée.")
    return f"🗑️ Bloc {block.id} (« {block.name} ») supprimé."


async def _tool_send_monitoring(args: dict) -> str:
    from app.bot.client import bot
    from app.bot.monitoring import refresh_block_now

    block = await _get_block(MonitoringRepository(), args)
    if not block.enabled:
        raise ValueError("Bloc inactif : active-le d'abord avec update_monitoring enabled=true.")
    if not bot.is_ready():
        raise RuntimeError("Bot Discord hors ligne.")
    if not await refresh_block_now(bot, block.id):
        raise RuntimeError("Mise à jour impossible (voir list_errors).")
    return f"✅ Bloc « {block.name} » envoyé / mis à jour sur Discord."


async def _tool_list_errors(args: dict) -> str:
    from app import log_buffer

    limit = max(1, min(100, int(args.get("limit") or 20)))
    failed = await LogRepository().list_recent(limit=limit, success=False)
    server = log_buffer.recent(limit)
    parts = []
    if failed:
        parts.append(f"❌ {len(failed)} échec(s) dans l'historique :\n" + "\n".join(_log_line(l) for l in failed))
    else:
        parts.append("Aucun échec dans l'historique.")
    if server:
        parts.append(
            f"⚠️ {len(server)} message(s) du serveur depuis le démarrage :\n"
            + "\n".join(f"{r['time']} [{r['level']}] {r['logger']} : {r['message']}" for r in server)
        )
    else:
        parts.append("Aucun avertissement ni erreur du serveur depuis le démarrage.")
    return "\n\n".join(parts)


async def _tool_list_colors(args: dict) -> str:
    presets = await SettingsRepository().get_color_presets()
    if not presets:
        return "Aucune couleur préconfigurée."
    lines = [f"- {c.get('name')} — #{int(c.get('color', 0)):06x}" for c in presets]
    return f"{len(presets)} couleur(s) :\n" + "\n".join(lines)


async def _tool_set_color(args: dict) -> str:
    repo = SettingsRepository()
    name = (args.get("name") or "").strip()
    raw = str(args.get("color") or "").strip().lstrip("#")
    try:
        value = int(raw, 16)
    except ValueError:
        raise ValueError(f"Couleur invalide : {args.get('color')!r} (attendu : hex, ex. #e8c547).") from None
    new_name = (args.get("new_name") or "").strip() or name
    preset = ColorPreset(name=new_name, color=value)
    presets = list(await repo.get_color_presets())
    if new_name != name and any(c.get("name") == new_name for c in presets):
        raise ValueError(f"La couleur « {new_name} » existe déjà.")
    idx = next((i for i, c in enumerate(presets) if c.get("name") == name), None)
    if idx is None:
        presets.append(preset.model_dump())
        verb = "créée"
    else:
        presets[idx] = preset.model_dump()
        verb = "modifiée"
    await repo.set("color_presets", presets)
    return f"✅ Couleur « {new_name} » (#{value:06x}) {verb}."


async def _tool_delete_color(args: dict) -> str:
    repo = SettingsRepository()
    name = (args.get("name") or "").strip()
    presets = await repo.get_color_presets()
    kept = [c for c in presets if c.get("name") != name]
    if len(kept) == len(presets):
        raise ValueError(f"Couleur « {name} » introuvable.")
    await repo.set("color_presets", kept)
    return f"🗑️ Couleur « {name} » supprimée."


HANDLERS.update({
    "list_commands": _tool_list_commands,
    "get_command": _tool_get_command,
    "create_command": _tool_create_command,
    "update_command": _tool_update_command,
    "delete_command": _tool_delete_command,
    "run_command": _tool_run_command,
    "list_monitoring": _tool_list_monitoring,
    "get_monitoring": _tool_get_monitoring,
    "create_monitoring": _tool_create_monitoring,
    "update_monitoring": _tool_update_monitoring,
    "delete_monitoring": _tool_delete_monitoring,
    "send_monitoring": _tool_send_monitoring,
    "list_errors": _tool_list_errors,
    "list_colors": _tool_list_colors,
    "set_color": _tool_set_color,
    "delete_color": _tool_delete_color,
})


# ======================================================================
#  Duplication, aperçus, salons Discord, fils, stats, système, réglages
# ======================================================================
def _id_schema(desc: str = "Id du bloc (voir list_monitoring).") -> dict:
    return {
        "type": "object",
        "properties": {"id": {"type": "integer", "description": desc}},
        "required": ["id"],
    }


_CONFIRM_PROP = {"type": "string", "description": "Mettre \"OUI\" pour appliquer. Sinon, simple aperçu."}

TOOLS.extend([
    {
        "name": "get_notification",
        "description": "Détail complet d'une notification (par slug), utile avant de la modifier.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "duplicate_notification",
        "description": "Duplique une notification. Slug de la copie : new_slug, sinon <slug>_copy.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Notification à copier."},
                "new_slug": {"type": "string", "description": "Slug de la copie (optionnel, a-z0-9_)."},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "preview_notification",
        "description": "Aperçu d'une notification avec les vraies valeurs Home Assistant, SANS l'envoyer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "variables": {
                    "type": "object",
                    "description": "Valeurs pour les {var:nom} (optionnel).",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["slug"],
        },
    },
    {
        "name": "duplicate_command",
        "description": "Duplique une commande slash (copie nommée <nom>-copie, créée désactivée).",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "duplicate_monitoring",
        "description": "Duplique un bloc de monitoring (copie créée inactive).",
        "inputSchema": _id_schema(),
    },
    {
        "name": "list_channels",
        "description": "Liste les salons du serveur Discord (nom, catégorie, id), pour trouver l'id d'un salon "
        "à partir de son nom. kind=forum pour les forums.",
        "inputSchema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["text", "forum"], "description": "Défaut : text."}},
        },
    },
    {
        "name": "list_forum_posts",
        "description": "Liste les posts actifs d'un salon forum Discord.",
        "inputSchema": {
            "type": "object",
            "properties": {"channel_id": {"type": "string", "description": "Id du salon forum."}},
            "required": ["channel_id"],
        },
    },
    {
        "name": "list_favorite_channels",
        "description": "Liste les salons favoris (raccourcis proposés dans les éditeurs du site).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_favorite_channel",
        "description": "Ajoute un salon favori, ou le modifie si le nom existe déjà. new_name pour le renommer.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom affiché du favori."},
                "channel_id": {"type": "string", "description": "Id du salon Discord (voir list_channels)."},
                "new_name": {"type": "string", "description": "Nouveau nom (optionnel)."},
            },
            "required": ["name", "channel_id"],
        },
    },
    {
        "name": "delete_favorite_channel",
        "description": "Supprime un salon favori (par son nom). Le salon Discord n'est pas touché.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_threads",
        "description": "Liste les fils Discord mémorisés pour les groupes de notifications (groupe, salon, fil).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_thread",
        "description": "Oublie le fil Discord d'un groupe (par id, voir list_threads) : le prochain envoi du "
        "groupe en créera un nouveau. Le fil existant sur Discord n'est pas supprimé.",
        "inputSchema": _id_schema("Id de l'entrée (voir list_threads)."),
    },
    {
        "name": "get_stats",
        "description": "Statistiques du tableau de bord : bot, Home Assistant, envois/erreurs/clics du jour, "
        "activité de la semaine et envois des 7 derniers jours.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "purge_history",
        "description": "Supprime les entrées d'historique plus vieilles que N jours. "
        "SÉCURITÉ : n'agit QUE si confirm vaut \"OUI\" ; sinon, aperçu.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "minimum": 1, "description": "Garder les N derniers jours."},
                "confirm": _CONFIRM_PROP,
            },
            "required": ["days"],
        },
    },
    {
        "name": "get_system_info",
        "description": "Infos système : version (commit), branche et dossier d'installation du site.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "restart_site",
        "description": "Redémarre le service BotPanel (sans mise à jour). "
        "SÉCURITÉ : n'agit QUE si confirm vaut \"OUI\".",
        "inputSchema": {"type": "object", "properties": {"confirm": _CONFIRM_PROP}},
    },
    {
        "name": "get_home_url",
        "description": "Lit l'URL d'accueil réglée dans les Paramètres.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_home_url",
        "description": "Change l'URL d'accueil des Paramètres (vide pour l'effacer).",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
])


async def _call_route(coro):
    """Appelle une route du site et traduit ses HTTPException en erreur d'outil lisible."""
    from fastapi import HTTPException

    try:
        return await coro
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from None


async def _get_notification(repo: NotificationRepository, args: dict):
    slug = (args.get("slug") or "").strip()
    notif = await repo.get_by_slug(slug)
    if notif is None:
        raise ValueError(f"Notification '{slug}' introuvable.")
    return notif


async def _tool_get_notification(args: dict) -> str:
    notif = await _get_notification(NotificationRepository(), args)
    data = notif.model_dump()
    data["color"] = f"#{notif.color:06x}"
    return json.dumps(data, ensure_ascii=False, indent=2)


async def _tool_duplicate_notification(args: dict) -> str:
    from app.api.routes.notifications import duplicate_notification

    repo = NotificationRepository()
    src = await _get_notification(repo, args)
    new_slug = (args.get("new_slug") or "").strip()
    if new_slug:
        if await repo.get_by_slug(new_slug) is not None:
            raise ValueError(f"Le slug '{new_slug}' existe déjà.")
        payload = NotificationIn(
            **{**src.model_dump(exclude={"id"}), "slug": new_slug, "title": f"{src.title} (copie)"}
        )
        copy = await repo.create(payload)
    else:
        copy = await _call_route(duplicate_notification(src.id))
    return f"✅ Notification '{src.slug}' dupliquée → '{copy.slug}' (id {copy.id})."


async def _tool_preview_notification(args: dict) -> str:
    from app.bot.notifications import _resolve_template

    notif = await _get_notification(NotificationRepository(), args)
    variables = args.get("variables") or None

    async def r(text: str | None) -> str:
        if not text:
            return ""
        try:
            return await _resolve_template(text, variables, resolve_vars=bool(variables))
        except Exception:  # noqa: BLE001 — l'aperçu ne doit jamais planter
            return text

    lines = [f"Titre : {await r(notif.title)}", f"Message :\n{await r(notif.message)}"]
    for f in notif.fields:
        lines.append(f"• {await r(f.name)} : {await r(f.value_template)}")
    if notif.footer:
        lines.append(f"Pied : {await r(notif.footer)}")
    for label, url in (("Miniature", notif.icon_url), ("Image", notif.image_url)):
        if url:
            lines.append(f"{label} : {await r(url)}")
    if notif.buttons:
        lines.append("Boutons : " + ", ".join(f"« {b.label} » ({b.ha_service})" for b in notif.buttons))
    lines.append(f"Salon : {notif.channel_id} · couleur #{notif.color:06x}")
    return "Aperçu (non envoyé) :\n" + "\n".join(lines)


async def _tool_duplicate_command(args: dict) -> str:
    from app.api.routes.slash_commands import duplicate_command

    cmd = await _get_command(SlashCommandRepository(), args)
    copy = await _call_route(duplicate_command(cmd.id))
    return f"✅ /{cmd.name} dupliquée → /{copy.name} (désactivée ; active-la avec update_command enabled=true)."


async def _tool_duplicate_monitoring(args: dict) -> str:
    from app.api.routes.monitoring import duplicate_block

    block = await _get_block(MonitoringRepository(), args)
    copy = await _call_route(duplicate_block(block.id))
    return f"✅ Bloc {block.id} dupliqué → « {copy.name} » (id {copy.id}, inactif)."


async def _tool_list_channels(args: dict) -> str:
    from app.api.routes.discord import list_forum_channels, list_text_channels
    from app.bot.client import bot

    if not bot.is_ready():
        raise RuntimeError("Bot Discord hors ligne : impossible de lister les salons.")
    forum = args.get("kind") == "forum"
    channels = await (list_forum_channels() if forum else list_text_channels())
    if not channels:
        return "Aucun salon trouvé."
    lines = [
        f"- #{c['name']} — id {c['id']}" + (f"  [{c['category']}]" if c.get("category") else "")
        for c in channels
    ]
    return f"{len(channels)} salon(s) {'forum' if forum else 'texte'} :\n" + "\n".join(lines)


async def _tool_list_forum_posts(args: dict) -> str:
    from app.api.routes.discord import list_forum_posts
    from app.bot.client import bot

    if not bot.is_ready():
        raise RuntimeError("Bot Discord hors ligne.")
    posts = await list_forum_posts(str(args.get("channel_id") or ""))
    if not posts:
        return "Aucun post actif (ou ce n'est pas un salon forum)."
    lines = [f"- {p['name']} — id {p['id']} · {p['message_count']} message(s)" for p in posts]
    return f"{len(posts)} post(s) :\n" + "\n".join(lines)


async def _tool_list_favorite_channels(args: dict) -> str:
    favs = await SettingsRepository().get_channel_presets()
    if not favs:
        return "Aucun salon favori."
    return f"{len(favs)} favori(s) :\n" + "\n".join(f"- {c.get('name')} — id {c.get('channel_id')}" for c in favs)


async def _tool_set_favorite_channel(args: dict) -> str:
    repo = SettingsRepository()
    name = (args.get("name") or "").strip()
    new_name = (args.get("new_name") or "").strip() or name
    preset = ChannelPreset(name=new_name, channel_id=str(args.get("channel_id") or "").strip())
    favs = list(await repo.get_channel_presets())
    if new_name != name and any(c.get("name") == new_name for c in favs):
        raise ValueError(f"Le favori « {new_name} » existe déjà.")
    idx = next((i for i, c in enumerate(favs) if c.get("name") == name), None)
    if idx is None:
        favs.append(preset.model_dump())
        verb = "ajouté"
    else:
        favs[idx] = preset.model_dump()
        verb = "modifié"
    await repo.set("channel_presets", favs)
    return f"✅ Favori « {new_name} » (salon {preset.channel_id}) {verb}."


async def _tool_delete_favorite_channel(args: dict) -> str:
    repo = SettingsRepository()
    name = (args.get("name") or "").strip()
    favs = await repo.get_channel_presets()
    kept = [c for c in favs if c.get("name") != name]
    if len(kept) == len(favs):
        raise ValueError(f"Favori « {name} » introuvable.")
    await repo.set("channel_presets", kept)
    return f"🗑️ Favori « {name} » supprimé."


async def _tool_list_threads(args: dict) -> str:
    threads = await ThreadRepository().list_all()
    if not threads:
        return "Aucun fil mémorisé."
    lines = [
        f"- id {t.id} · groupe « {t.group_name} » · salon {t.channel_id} · fil {t.thread_id} · depuis {t.created_at}"
        for t in threads
    ]
    return f"{len(threads)} fil(s) :\n" + "\n".join(lines)


async def _tool_delete_thread(args: dict) -> str:
    try:
        entry_id = int(args.get("id"))
    except (TypeError, ValueError):
        raise ValueError("Le paramètre 'id' (entier) est requis — voir list_threads.") from None
    if not await ThreadRepository().delete(entry_id):
        raise ValueError(f"Fil {entry_id} introuvable.")
    return f"🗑️ Fil {entry_id} oublié : le prochain envoi du groupe en créera un nouveau."


async def _tool_get_stats(args: dict) -> str:
    from app.api.routes.dashboard import dashboard_stats

    s = await dashboard_stats()
    bot_txt = f"🟢 en ligne ({s['bot_latency_ms']} ms)" if s["bot_ready"] else "🔴 hors ligne"
    days = "\n".join(f"  {d['day']} : {d['sent']} envoi(s), {d['errors']} erreur(s)" for d in s["daily"])
    return (
        f"Bot Discord : {bot_txt}\n"
        f"Home Assistant : {'🟢 joignable' if s['ha_ok'] else '🔴 injoignable'}\n"
        f"Aujourd'hui : {s['sent_today']} envoi(s), {s['errors_today']} erreur(s), {s['clicks_today']} clic(s)\n"
        f"Activité sur 7 jours : {s['activity_week']}\n"
        f"Notifications : {s['notifications_total']} · monitoring : "
        f"{s['monitoring_enabled']}/{s['monitoring_total']} bloc(s) actif(s)\n"
        f"Envois des 7 derniers jours :\n{days}"
    )


async def _tool_purge_history(args: dict) -> str:
    try:
        days = int(args.get("days"))
    except (TypeError, ValueError):
        raise ValueError("Le paramètre 'days' (entier) est requis.") from None
    if days < 1:
        raise ValueError("'days' doit valoir au moins 1.")
    if not _confirmed(args):
        return (
            f"⚠️ Confirmation requise — je supprimerais l'historique de plus de {days} jour(s). "
            f"Relance avec confirm=\"OUI\" pour appliquer."
        )
    n = await LogRepository().purge_older_than(days)
    return f"🗑️ {n} entrée(s) d'historique de plus de {days} jour(s) supprimée(s)."


async def _tool_get_system_info(args: dict) -> str:
    from app.api.routes.system import system_info

    info = await system_info()
    if not info.get("is_git"):
        return f"Dossier : {info['install_dir']} (pas un dépôt git)."
    return f"Commit : {info.get('commit')} · branche : {info.get('branch')} · dossier : {info['install_dir']}"


async def _tool_restart_site(args: dict) -> str:
    if not _confirmed(args):
        return "⚠️ Confirmation requise — relance avec confirm=\"OUI\" pour redémarrer BotPanel."
    _schedule_restart()
    return "🔄 Redémarrage en cours… reconnecte le connecteur dans ~10 s."


async def _tool_get_home_url(args: dict) -> str:
    url = await SettingsRepository().get("home_url", "")
    return f"URL d'accueil : {url}" if url else "Aucune URL d'accueil réglée."


async def _tool_set_home_url(args: dict) -> str:
    url = str(args.get("url") or "").strip()
    await SettingsRepository().set("home_url", url)
    return f"✅ URL d'accueil : {url}" if url else "✅ URL d'accueil effacée."


HANDLERS.update({
    "get_notification": _tool_get_notification,
    "duplicate_notification": _tool_duplicate_notification,
    "preview_notification": _tool_preview_notification,
    "duplicate_command": _tool_duplicate_command,
    "duplicate_monitoring": _tool_duplicate_monitoring,
    "list_channels": _tool_list_channels,
    "list_forum_posts": _tool_list_forum_posts,
    "list_favorite_channels": _tool_list_favorite_channels,
    "set_favorite_channel": _tool_set_favorite_channel,
    "delete_favorite_channel": _tool_delete_favorite_channel,
    "list_threads": _tool_list_threads,
    "delete_thread": _tool_delete_thread,
    "get_stats": _tool_get_stats,
    "purge_history": _tool_purge_history,
    "get_system_info": _tool_get_system_info,
    "restart_site": _tool_restart_site,
    "get_home_url": _tool_get_home_url,
    "set_home_url": _tool_set_home_url,
})


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
