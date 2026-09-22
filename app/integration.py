"""Integration machine (Home Assistant) : cle API + suivi de connexion.

La cle API (`X-API-Key`) protege les endpoints /api/integration/* appeles par
des machines (le composant Home Assistant). Elle est stockee dans le store
(table settings, cle `integration_api_key`), avec repli sur la variable d'env
`INTEGRATION_API_KEY` a la premiere install.

Rien a voir avec le login humain : ces routes restent hors du garde humain et se
protegent uniquement par la cle. `/api/notify` (webhooks existants) reste ouvert.
"""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timezone

from app.config import settings as app_settings
from app.db.repositories import SettingsRepository

_KEY_SETTING = "integration_api_key"
_LAST_SEEN_SETTING = "integration_last_seen"
_HEADER = "x-api-key"


def gen_key() -> str:
    """Genere une cle API aleatoire (URL-safe)."""
    return secrets.token_urlsafe(32)


async def get_api_key() -> str:
    """Cle API effective : store prioritaire, sinon variable d'env, sinon ''."""
    repo = SettingsRepository()
    key = await repo.get(_KEY_SETTING, None)
    if key is None:
        key = app_settings.integration_api_key
    return (key or "").strip()


async def set_api_key(key: str) -> None:
    repo = SettingsRepository()
    await repo.set(_KEY_SETTING, (key or "").strip())


async def ensure_api_key() -> str:
    """Renvoie la cle, en la generant+stockant si aucune n'existe encore."""
    key = await get_api_key()
    if not key:
        key = gen_key()
        await set_api_key(key)
    return key


async def regenerate_key() -> str:
    """Regenere une nouvelle cle (invalide l'ancienne) et la renvoie."""
    key = gen_key()
    await set_api_key(key)
    return key


def _request_key(request) -> str:
    """Extrait la cle presentee : en-tete X-API-Key, sinon ?api_key=."""
    return (request.headers.get(_HEADER)
            or request.query_params.get("api_key")
            or "").strip()


async def verify_api_key(request) -> bool:
    """True si la requete presente la bonne cle API (comparaison constante)."""
    stored = await get_api_key()
    presented = _request_key(request)
    if not stored or not presented:
        return False
    return hmac.compare_digest(stored, presented)


async def touch_last_seen() -> None:
    """Memorise l'instant du dernier appel machine valide (pour le diagnostic)."""
    repo = SettingsRepository()
    await repo.set(_LAST_SEEN_SETTING, datetime.now(timezone.utc).isoformat())


async def get_last_seen() -> str | None:
    repo = SettingsRepository()
    return await repo.get(_LAST_SEEN_SETTING, None)
