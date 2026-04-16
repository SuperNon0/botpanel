"""Repository des blocs de monitoring."""

from __future__ import annotations

from typing import Optional

from app.db.database import get_connection
from app.db.models import MonitoringBlock, MonitoringBlockIn


class MonitoringRepository:
    """Gestion des blocs de monitoring (temperature, conso electrique...)."""

    async def list_all(self) -> list[MonitoringBlock]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM monitoring_blocks ORDER BY block_type"
            )
            return [self._row_to_model(r) for r in rows]

    async def get_by_type(self, block_type: str) -> Optional[MonitoringBlock]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM monitoring_blocks WHERE block_type = ?", (block_type,)
            )
            row = await cursor.fetchone()
            return self._row_to_model(row) if row else None

    async def update(self, block_type: str, payload: MonitoringBlockIn) -> Optional[MonitoringBlock]:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE monitoring_blocks SET
                    enabled = ?, channel_id = ?, interval_seconds = ?,
                    config_json = ?, updated_at = datetime('now')
                WHERE block_type = ?
                """,
                (
                    int(payload.enabled), payload.channel_id,
                    payload.interval_seconds, payload.config_json, block_type,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await db.commit()
        return await self.get_by_type(block_type)

    async def set_message_id(self, block_type: str, message_id: Optional[str]) -> None:
        """Memorise l'ID du message epingle apres son premier envoi."""
        async with get_connection() as db:
            await db.execute(
                "UPDATE monitoring_blocks SET message_id = ? WHERE block_type = ?",
                (message_id, block_type),
            )
            await db.commit()

    def _row_to_model(self, row) -> MonitoringBlock:
        return MonitoringBlock(
            id=row["id"],
            block_type=row["block_type"],
            enabled=bool(row["enabled"]),
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            interval_seconds=row["interval_seconds"],
            config_json=row["config_json"],
        )
