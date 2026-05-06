"""Repository CRUD pour les notifications Proxmox."""

from __future__ import annotations

from typing import Optional

from app.db.database import get_connection
from app.db.models import (
    ProxmoxEventType,
    ProxmoxField,
    ProxmoxNotification,
    ProxmoxNotificationIn,
)


class ProxmoxNotificationRepository:
    """CRUD proxmox_notifications + proxmox_notification_fields."""

    async def list_all(self) -> list[ProxmoxNotification]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM proxmox_notifications ORDER BY name"
            )
            result: list[ProxmoxNotification] = []
            for row in rows:
                fields = await self._list_fields(db, row["id"])
                result.append(self._row_to_model(row, fields))
            return result

    async def list_by_event(self, event_type: str) -> list[ProxmoxNotification]:
        """Retourne les notifications activees qui correspondent a l'evenement."""
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                """SELECT * FROM proxmox_notifications
                   WHERE enabled = 1 AND (event_type = ? OR event_type = 'any')
                   ORDER BY id""",
                (event_type,),
            )
            result: list[ProxmoxNotification] = []
            for row in rows:
                fields = await self._list_fields(db, row["id"])
                result.append(self._row_to_model(row, fields))
            return result

    async def get_by_id(self, notif_id: int) -> Optional[ProxmoxNotification]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM proxmox_notifications WHERE id = ?", (notif_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            fields = await self._list_fields(db, row["id"])
            return self._row_to_model(row, fields)

    async def create(self, payload: ProxmoxNotificationIn) -> ProxmoxNotification:
        async with get_connection() as db:
            cursor = await db.execute(
                """INSERT INTO proxmox_notifications
                   (name, event_type, enabled, channel_id, title, message,
                    color, icon_url, footer, show_timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload.name, payload.event_type, int(payload.enabled),
                    payload.channel_id, payload.title, payload.message,
                    payload.color, payload.icon_url, payload.footer,
                    int(payload.show_timestamp),
                ),
            )
            notif_id = cursor.lastrowid
            await self._replace_fields(db, notif_id, payload.fields)
            await db.commit()
        result = await self.get_by_id(notif_id)
        assert result is not None
        return result

    async def update(
        self, notif_id: int, payload: ProxmoxNotificationIn
    ) -> Optional[ProxmoxNotification]:
        async with get_connection() as db:
            cursor = await db.execute(
                """UPDATE proxmox_notifications SET
                   name = ?, event_type = ?, enabled = ?, channel_id = ?,
                   title = ?, message = ?, color = ?, icon_url = ?,
                   footer = ?, show_timestamp = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (
                    payload.name, payload.event_type, int(payload.enabled),
                    payload.channel_id, payload.title, payload.message,
                    payload.color, payload.icon_url, payload.footer,
                    int(payload.show_timestamp), notif_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await self._replace_fields(db, notif_id, payload.fields)
            await db.commit()
        return await self.get_by_id(notif_id)

    async def delete(self, notif_id: int) -> bool:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM proxmox_notifications WHERE id = ?", (notif_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    # -------- internes --------
    async def _list_fields(self, db, notif_id: int) -> list[ProxmoxField]:
        cursor = await db.execute(
            """SELECT id, position, name, value_template, inline
               FROM proxmox_notification_fields
               WHERE proxmox_notification_id = ?
               ORDER BY position, id""",
            (notif_id,),
        )
        rows = await cursor.fetchall()
        return [
            ProxmoxField(
                id=row["id"],
                position=row["position"],
                name=row["name"],
                value_template=row["value_template"],
                inline=bool(row["inline"]),
            )
            for row in rows
        ]

    async def _replace_fields(self, db, notif_id: int, fields: list[ProxmoxField]) -> None:
        await db.execute(
            "DELETE FROM proxmox_notification_fields WHERE proxmox_notification_id = ?",
            (notif_id,),
        )
        for idx, fld in enumerate(fields):
            await db.execute(
                """INSERT INTO proxmox_notification_fields
                   (proxmox_notification_id, position, name, value_template, inline)
                   VALUES (?, ?, ?, ?, ?)""",
                (notif_id, fld.position or idx, fld.name, fld.value_template, int(fld.inline)),
            )

    def _row_to_model(self, row, fields: list[ProxmoxField]) -> ProxmoxNotification:
        return ProxmoxNotification(
            id=row["id"],
            name=row["name"],
            event_type=row["event_type"],
            enabled=bool(row["enabled"]),
            channel_id=row["channel_id"],
            title=row["title"],
            message=row["message"],
            color=row["color"],
            icon_url=row["icon_url"],
            footer=row["footer"],
            show_timestamp=bool(row["show_timestamp"]),
            fields=fields,
        )
