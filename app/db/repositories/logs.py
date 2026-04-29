"""Repository des logs (envois de notifications + clics de boutons)."""

from __future__ import annotations

from typing import Optional

from app.db.database import get_connection
from app.db.models import NotificationLog


class LogRepository:
    """Append-only : on n'edite jamais une ligne existante."""

    async def add(
        self,
        *,
        kind: str,
        notification_id: Optional[int] = None,
        notification_slug: Optional[str] = None,
        channel_id: Optional[str] = None,
        message_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        button_label: Optional[str] = None,
        detail: Optional[str] = None,
        success: bool = True,
    ) -> int:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO notification_logs (
                    notification_id, notification_slug, channel_id, message_id,
                    kind, user_id, user_name, button_label, detail, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id, notification_slug, channel_id, message_id,
                    kind, user_id, user_name, button_label, detail, int(success),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def list_recent(
        self,
        *,
        limit: int = 200,
        kind: Optional[str] = None,
        notification_id: Optional[int] = None,
    ) -> list[NotificationLog]:
        clauses: list[str] = []
        params: list = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if notification_id is not None:
            clauses.append("notification_id = ?")
            params.append(notification_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        async with get_connection() as db:
            cursor = await db.execute(
                f"""
                SELECT * FROM notification_logs
                {where}
                ORDER BY id DESC
                LIMIT ?
                """,
                params,
            )
            rows = await cursor.fetchall()

        return [
            NotificationLog(
                id=row["id"],
                notification_id=row["notification_id"],
                notification_slug=row["notification_slug"],
                channel_id=row["channel_id"],
                message_id=row["message_id"],
                kind=row["kind"],
                user_id=row["user_id"],
                user_name=row["user_name"],
                button_label=row["button_label"],
                detail=row["detail"],
                success=bool(row["success"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def purge_older_than(self, days: int) -> int:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM notification_logs WHERE created_at < datetime('now', ?)",
                (f"-{int(days)} days",),
            )
            await db.commit()
            return cursor.rowcount or 0
