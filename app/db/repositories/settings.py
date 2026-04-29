"""Repository des settings globaux (key/value JSON)."""

from __future__ import annotations

import json
from typing import Any

from app.db.database import get_connection


DEFAULT_COLOR_PRESETS = [
    {"name": "Jaune (alerte)", "color": 0xE8C547},
    {"name": "Vert (OK)", "color": 0x4ADE80},
    {"name": "Rouge (erreur)", "color": 0xEF4444},
    {"name": "Orange (attention)", "color": 0xF59E0B},
    {"name": "Violet (Discord)", "color": 0x8B5CF6},
    {"name": "Bleu (HA)", "color": 0x49A0DF},
]


class SettingsRepository:
    """Acces simple a la table key/value JSON."""

    async def get(self, key: str, default: Any = None) -> Any:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT value_json FROM settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            if row is None:
                return default
            try:
                return json.loads(row["value_json"])
            except (TypeError, ValueError):
                return default

    async def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        async with get_connection() as db:
            await db.execute(
                """
                INSERT INTO settings (key, value_json, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = datetime('now')
                """,
                (key, payload),
            )
            await db.commit()

    async def get_color_presets(self) -> list[dict]:
        return await self.get("color_presets", DEFAULT_COLOR_PRESETS)

    async def get_channel_presets(self) -> list[dict]:
        return await self.get("channel_presets", [])
