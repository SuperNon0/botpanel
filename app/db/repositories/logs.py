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

    async def stats_today(self) -> dict:
        """Compte les envois/erreurs/clics depuis minuit (UTC)."""
        async with get_connection() as db:
            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN kind='send'  AND success=1 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN kind='send'  AND success=0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN kind IN ('button','snooze','delete') THEN 1 ELSE 0 END)
                FROM notification_logs
                WHERE created_at >= date('now')
                """
            )
            row = await cursor.fetchone()
            return {
                "sent_ok": row[0] or 0,
                "sent_err": row[1] or 0,
                "clicks": row[2] or 0,
            }

    async def count_week(self) -> int:
        """Compte tous les evenements des 7 derniers jours."""
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM notification_logs WHERE created_at >= datetime('now', '-7 days')"
            )
            row = await cursor.fetchone()
            return row[0] or 0

    async def daily_counts(self, days: int = 7) -> list[dict]:
        """Retourne le nombre d'envois reussis par jour sur les N derniers jours."""
        async with get_connection() as db:
            cursor = await db.execute(
                """
                SELECT date(created_at) as day,
                       SUM(CASE WHEN kind='send' AND success=1 THEN 1 ELSE 0 END) as sent,
                       SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors
                FROM notification_logs
                WHERE created_at >= date('now', ?)
                GROUP BY date(created_at)
                ORDER BY day ASC
                """,
                (f"-{days} days",),
            )
            rows = await cursor.fetchall()
            by_day = {row["day"]: {"sent": row["sent"], "errors": row["errors"]} for row in rows}

        import datetime
        result = []
        today = datetime.date.today()
        for i in range(days - 1, -1, -1):
            d = str(today - datetime.timedelta(days=i))
            v = by_day.get(d, {"sent": 0, "errors": 0})
            result.append({"day": d, "sent": v["sent"], "errors": v["errors"]})
        return result

    async def purge_older_than(self, days: int) -> int:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM notification_logs WHERE created_at < datetime('now', ?)",
                (f"-{int(days)} days",),
            )
            await db.commit()
            return cursor.rowcount or 0
