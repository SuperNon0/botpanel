"""Boutons « webhook » : au clic, BotPanel fait un POST JSON vers une URL.

Le corps est signe en HMAC-SHA256 avec le secret webhook (Parametres >
Integrations), envoye dans l'en-tete `X-BotPanel-Signature: sha256=<hex>`.
Le site appele peut ainsi verifier que l'appel vient bien de BotPanel.

Reponse attendue (facultative) : un JSON `{"message": "..."}` dont le texte est
affiche a la personne qui a clique (sinon « ✅ <bouton> execute »).

Les variables `{var:...}` passees a l'envoi d'une notification sont gardees
(table `message_vars`) pour etre resolues au moment du clic, dans l'URL et
dans les valeurs texte des donnees JSON.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from typing import Any

import httpx

from app.db.database import get_connection
from app.db.repositories import SettingsRepository

logger = logging.getLogger(__name__)

_SECRET_SETTING = "webhook_secret"
SIGNATURE_HEADER = "X-BotPanel-Signature"
TIMESTAMP_HEADER = "X-BotPanel-Timestamp"
_TIMEOUT = 10.0
_VARS_TTL_DAYS = 30

VAR_RE = re.compile(r"\{var:([a-zA-Z0-9_]+)(?:\|([^}]*))?\}")


class WebhookError(Exception):
    """Echec d'appel d'un bouton webhook (message lisible pour Discord)."""


# ----------------------------------------------------------------------
# Secret de signature
# ----------------------------------------------------------------------
async def get_webhook_secret() -> str:
    """Secret de signature, genere au premier besoin."""
    repo = SettingsRepository()
    secret = (await repo.get(_SECRET_SETTING, "") or "").strip()
    if not secret:
        secret = secrets.token_urlsafe(32)
        await repo.set(_SECRET_SETTING, secret)
    return secret


async def regenerate_webhook_secret() -> str:
    secret = secrets.token_urlsafe(32)
    await SettingsRepository().set(_SECRET_SETTING, secret)
    return secret


def sign(secret: str, timestamp: str, body: bytes) -> str:
    """Signature envoyee : HMAC-SHA256 de "<timestamp>.<corps>"."""
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


# ----------------------------------------------------------------------
# Variables gardees par message
# ----------------------------------------------------------------------
async def store_message_vars(message_id: str, variables: dict | None) -> None:
    if not variables:
        return
    async with get_connection() as db:
        await db.execute(
            "DELETE FROM message_vars WHERE created_at < datetime('now', ?)",
            (f"-{_VARS_TTL_DAYS} days",),
        )
        await db.execute(
            "INSERT OR REPLACE INTO message_vars (message_id, vars_json) VALUES (?, ?)",
            (message_id, json.dumps(variables, ensure_ascii=False, default=str)),
        )
        await db.commit()


async def load_message_vars(message_id: str | None) -> dict:
    if not message_id:
        return {}
    async with get_connection() as db:
        cursor = await db.execute(
            "SELECT vars_json FROM message_vars WHERE message_id = ?", (message_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        return {}
    try:
        data = json.loads(row["vars_json"])
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve_vars(text: str, variables: dict | None) -> str:
    """{var:nom} / {var:nom|defaut} -> valeur (meme regle que les notifications)."""
    if not text or "{var:" not in text:
        return text
    variables = variables or {}

    def repl(m: re.Match) -> str:
        value = variables.get(m.group(1))
        if value is None:
            return m.group(2) if m.group(2) is not None else ""
        return str(value)

    return VAR_RE.sub(repl, text)


def _resolve_in(obj: Any, variables: dict) -> Any:
    if isinstance(obj, str):
        return resolve_vars(obj, variables)
    if isinstance(obj, list):
        return [_resolve_in(x, variables) for x in obj]
    if isinstance(obj, dict):
        return {k: _resolve_in(v, variables) for k, v in obj.items()}
    return obj


# ----------------------------------------------------------------------
# Appel
# ----------------------------------------------------------------------
async def call_webhook(
    url: str,
    *,
    data_json: str | None,
    variables: dict | None,
    context: dict,
) -> str | None:
    """POST JSON signe vers `url`. Renvoie le `message` de la reponse, s'il y en a un.

    `context` : infos sur le clic (source, bouton, utilisateur, message…).
    Leve WebhookError si l'URL est invalide, injoignable ou repond en erreur.
    """
    variables = variables or {}
    target = resolve_vars((url or "").strip(), variables)
    if not target.lower().startswith(("http://", "https://")):
        raise WebhookError(f"URL de webhook invalide : {target or '(vide)'}")

    data: Any = {}
    if data_json:
        try:
            data = json.loads(data_json)
        except json.JSONDecodeError:
            logger.warning("Donnees JSON du webhook invalides ignorees : %r", data_json)
            data = {}

    payload = {
        "event": "button_click",
        **context,
        "vars": variables,
        "data": _resolve_in(data, variables),
    }
    body = json.dumps(payload, ensure_ascii=False, default=str).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "BotPanel-Webhook",
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(await get_webhook_secret(), timestamp, body),
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            resp = await client.post(target, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise WebhookError(f"site injoignable ({exc.__class__.__name__})") from exc

    if resp.status_code >= 400:
        raise WebhookError(f"le site a repondu {resp.status_code}")

    try:
        reply = resp.json()
    except ValueError:
        return None
    if isinstance(reply, dict) and reply.get("message"):
        return str(reply["message"])[:1800]
    return None
