"""Repository des commandes slash Discord."""

from __future__ import annotations

from typing import Optional

from app.db.database import get_connection
from app.db.models import SlashCommand, SlashCommandIn


MAX_SLASH_COMMANDS = 100  # Limite Discord


class SlashCommandRepository:
    """CRUD commandes slash."""

    async def list_all(self, only_enabled: bool = False) -> list[SlashCommand]:
        query = "SELECT * FROM slash_commands"
        if only_enabled:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        async with get_connection() as db:
            rows = await db.execute_fetchall(query)
            return [self._row_to_model(r) for r in rows]

    async def get_by_id(self, cmd_id: int) -> Optional[SlashCommand]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM slash_commands WHERE id = ?", (cmd_id,)
            )
            row = await cursor.fetchone()
            return self._row_to_model(row) if row else None

    async def count(self) -> int:
        async with get_connection() as db:
            cursor = await db.execute("SELECT COUNT(*) AS n FROM slash_commands")
            row = await cursor.fetchone()
            return row["n"] if row else 0

    async def create(self, payload: SlashCommandIn) -> SlashCommand:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO slash_commands (
                    name, description, action_type, ha_service, ha_entity_id,
                    ha_data_json, notification_slug, response_message, enabled
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name, payload.description, payload.action_type,
                    payload.ha_service, payload.ha_entity_id, payload.ha_data_json,
                    payload.notification_slug, payload.response_message,
                    int(payload.enabled),
                ),
            )
            cmd_id = cursor.lastrowid
            await db.commit()
        result = await self.get_by_id(cmd_id)
        assert result is not None
        return result

    async def update(self, cmd_id: int, payload: SlashCommandIn) -> Optional[SlashCommand]:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE slash_commands SET
                    name = ?, description = ?, action_type = ?, ha_service = ?,
                    ha_entity_id = ?, ha_data_json = ?, notification_slug = ?,
                    response_message = ?, enabled = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    payload.name, payload.description, payload.action_type,
                    payload.ha_service, payload.ha_entity_id, payload.ha_data_json,
                    payload.notification_slug, payload.response_message,
                    int(payload.enabled), cmd_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await db.commit()
        return await self.get_by_id(cmd_id)

    async def delete(self, cmd_id: int) -> bool:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM slash_commands WHERE id = ?", (cmd_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    def _row_to_model(self, row) -> SlashCommand:
        return SlashCommand(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            action_type=row["action_type"],
            ha_service=row["ha_service"],
            ha_entity_id=row["ha_entity_id"],
            ha_data_json=row["ha_data_json"],
            notification_slug=row["notification_slug"],
            response_message=row["response_message"],
            enabled=bool(row["enabled"]),
        )
