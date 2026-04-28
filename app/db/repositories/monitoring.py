"""Repository des blocs de monitoring (CRUD libre)."""

from __future__ import annotations

from typing import Optional

from app.db.database import get_connection
from app.db.models import MonitoringBlock, MonitoringBlockIn


class MonitoringRepository:
    """Gestion des blocs de monitoring custom."""

    async def list_all(self) -> list[MonitoringBlock]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM monitoring_blocks ORDER BY id"
            )
            return [self._row_to_model(r) for r in rows]

    async def get_by_id(self, block_id: int) -> Optional[MonitoringBlock]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM monitoring_blocks WHERE id = ?", (block_id,)
            )
            row = await cursor.fetchone()
            return self._row_to_model(row) if row else None

    async def create(self, payload: MonitoringBlockIn) -> MonitoringBlock:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO monitoring_blocks (
                    name, icon, color, enabled, channel_id,
                    interval_seconds, footer, config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.name, payload.icon, payload.color,
                    int(payload.enabled), payload.channel_id,
                    payload.interval_seconds, payload.footer, payload.config_json,
                ),
            )
            await db.commit()
            block_id = cursor.lastrowid
        result = await self.get_by_id(block_id)
        assert result is not None
        return result

    async def update(self, block_id: int, payload: MonitoringBlockIn) -> Optional[MonitoringBlock]:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE monitoring_blocks SET
                    name = ?, icon = ?, color = ?, enabled = ?, channel_id = ?,
                    interval_seconds = ?, footer = ?, config_json = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    payload.name, payload.icon, payload.color,
                    int(payload.enabled), payload.channel_id,
                    payload.interval_seconds, payload.footer, payload.config_json,
                    block_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await db.commit()
        return await self.get_by_id(block_id)

    async def delete(self, block_id: int) -> bool:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM monitoring_blocks WHERE id = ?", (block_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def set_message_id(self, block_id: int, message_id: Optional[str]) -> None:
        """Memorise l'ID du message epingle apres son premier envoi."""
        async with get_connection() as db:
            await db.execute(
                "UPDATE monitoring_blocks SET message_id = ? WHERE id = ?",
                (message_id, block_id),
            )
            await db.commit()

    def _row_to_model(self, row) -> MonitoringBlock:
        return MonitoringBlock(
            id=row["id"],
            name=row["name"] or "Bloc",
            icon=row["icon"],
            color=row["color"] if row["color"] is not None else 0x49A0DF,
            enabled=bool(row["enabled"]),
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            interval_seconds=row["interval_seconds"],
            footer=row["footer"],
            config_json=row["config_json"] or "{}",
        )
