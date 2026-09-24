"""Petit client HTTP vers l'API d'intégration BotPanel (/api/integration/*)."""
from __future__ import annotations

import asyncio

import aiohttp


class BotpanelApiError(Exception):
    """Erreur générique de communication avec BotPanel."""


class BotpanelAuthError(BotpanelApiError):
    """Clé API invalide (HTTP 401)."""


class BotpanelApi:
    """Accès aux endpoints machine de BotPanel, authentifiés par X-API-Key."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._key = api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self._key}

    async def _get(self, path: str):
        try:
            async with asyncio.timeout(10):
                async with self._session.get(self._base + path, headers=self._headers) as resp:
                    if resp.status == 401:
                        raise BotpanelAuthError("Clé API invalide")
                    resp.raise_for_status()
                    return await resp.json()
        except BotpanelApiError:
            raise
        except Exception as err:  # noqa: BLE001
            raise BotpanelApiError(str(err)) from err

    async def _post(self, path: str, payload: dict):
        try:
            async with asyncio.timeout(10):
                async with self._session.post(self._base + path, headers=self._headers, json=payload) as resp:
                    if resp.status == 401:
                        raise BotpanelAuthError("Clé API invalide")
                    resp.raise_for_status()
                    return await resp.json()
        except BotpanelApiError:
            raise
        except Exception as err:  # noqa: BLE001
            raise BotpanelApiError(str(err)) from err

    async def ping(self) -> dict:
        return await self._get("/api/integration/ping")

    async def notifications(self) -> list[dict]:
        return await self._get("/api/integration/notifications")

    async def state(self) -> dict:
        return await self._get("/api/integration/state")

    async def trigger(self, notif_id: int | None = None, slug: str | None = None) -> dict:
        return await self._post("/api/integration/trigger", {"id": notif_id, "slug": slug})
