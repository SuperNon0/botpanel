"""Repository pour les threads Discord persistants."""

from __future__ import annotations

from app.db.database import get_connection
from app.db.models import NotificationThread


class ThreadRepository:
    async def list_all(self) -> list[NotificationThread]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT id, group_name, channel_id, thread_id, created_at "
                "FROM notification_threads ORDER BY group_name, channel_id"
            )
            rows = await cursor.fetchall()
        return [NotificationThread(**dict(r)) for r in rows]

    async def get_thread_id(self, group_name: str, channel_id: str) -> str | None:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT thread_id FROM notification_threads "
                "WHERE group_name = ? AND channel_id = ?",
                (group_name, channel_id),
            )
            row = await cursor.fetchone()
        return row["thread_id"] if row else None

    async def upsert(self, group_name: str, channel_id: str, thread_id: str) -> None:
        async with get_connection() as db:
            await db.execute(
                """
                INSERT INTO notification_threads (group_name, channel_id, thread_id)
                VALUES (?, ?, ?)
                ON CONFLICT(group_name, channel_id) DO UPDATE SET thread_id = excluded.thread_id
                """,
                (group_name, channel_id, thread_id),
            )
            await db.commit()

    async def delete(self, entry_id: int) -> bool:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM notification_threads WHERE id = ?", (entry_id,)
            )
            await db.commit()
        return cursor.rowcount > 0
