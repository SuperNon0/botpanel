"""Repository des notifications, de leurs boutons et fields custom."""

from __future__ import annotations

from typing import Optional

from app.db.database import get_connection
from app.db.models import (
    Notification,
    NotificationButton,
    NotificationField,
    NotificationIn,
)


class NotificationRepository:
    """CRUD notifications + boutons + fields associes."""

    async def list_all(self) -> list[Notification]:
        async with get_connection() as db:
            rows = await db.execute_fetchall(
                "SELECT * FROM notifications ORDER BY slug"
            )
            notifs: list[Notification] = []
            for row in rows:
                buttons = await self._list_buttons(db, row["id"])
                fields = await self._list_fields(db, row["id"])
                notifs.append(self._row_to_model(row, buttons, fields))
            return notifs

    async def get_by_slug(self, slug: str) -> Optional[Notification]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM notifications WHERE slug = ?", (slug,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            buttons = await self._list_buttons(db, row["id"])
            fields = await self._list_fields(db, row["id"])
            return self._row_to_model(row, buttons, fields)

    async def get_by_id(self, notif_id: int) -> Optional[Notification]:
        async with get_connection() as db:
            cursor = await db.execute(
                "SELECT * FROM notifications WHERE id = ?", (notif_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            buttons = await self._list_buttons(db, row["id"])
            fields = await self._list_fields(db, row["id"])
            return self._row_to_model(row, buttons, fields)

    async def create(self, payload: NotificationIn) -> Notification:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                INSERT INTO notifications (
                    slug, channel_id, title, message, color, icon_url, footer,
                    show_timestamp, delete_button, snooze_button, snooze_minutes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.slug, payload.channel_id, payload.title, payload.message,
                    payload.color, payload.icon_url, payload.footer,
                    int(payload.show_timestamp), int(payload.delete_button),
                    int(payload.snooze_button), payload.snooze_minutes,
                ),
            )
            notif_id = cursor.lastrowid
            await self._replace_buttons(db, notif_id, payload.buttons)
            await self._replace_fields(db, notif_id, payload.fields)
            await db.commit()
        result = await self.get_by_id(notif_id)
        assert result is not None
        return result

    async def update(self, notif_id: int, payload: NotificationIn) -> Optional[Notification]:
        async with get_connection() as db:
            cursor = await db.execute(
                """
                UPDATE notifications SET
                    slug = ?, channel_id = ?, title = ?, message = ?, color = ?,
                    icon_url = ?, footer = ?, show_timestamp = ?, delete_button = ?,
                    snooze_button = ?, snooze_minutes = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    payload.slug, payload.channel_id, payload.title, payload.message,
                    payload.color, payload.icon_url, payload.footer,
                    int(payload.show_timestamp), int(payload.delete_button),
                    int(payload.snooze_button), payload.snooze_minutes, notif_id,
                ),
            )
            if cursor.rowcount == 0:
                return None
            await self._replace_buttons(db, notif_id, payload.buttons)
            await self._replace_fields(db, notif_id, payload.fields)
            await db.commit()
        return await self.get_by_id(notif_id)

    async def delete(self, notif_id: int) -> bool:
        async with get_connection() as db:
            cursor = await db.execute(
                "DELETE FROM notifications WHERE id = ?", (notif_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    # -------- internes --------
    async def _list_buttons(self, db, notif_id: int) -> list[NotificationButton]:
        cursor = await db.execute(
            """
            SELECT id, position, label, style, emoji, ha_service, ha_entity_id, ha_data_json
            FROM notification_buttons
            WHERE notification_id = ?
            ORDER BY position, id
            """,
            (notif_id,),
        )
        rows = await cursor.fetchall()
        return [NotificationButton(**dict(row)) for row in rows]

    async def _list_fields(self, db, notif_id: int) -> list[NotificationField]:
        cursor = await db.execute(
            """
            SELECT id, position, name, value_template, inline
            FROM notification_fields
            WHERE notification_id = ?
            ORDER BY position, id
            """,
            (notif_id,),
        )
        rows = await cursor.fetchall()
        return [
            NotificationField(
                id=row["id"],
                position=row["position"],
                name=row["name"],
                value_template=row["value_template"],
                inline=bool(row["inline"]),
            )
            for row in rows
        ]

    async def _replace_buttons(self, db, notif_id: int, buttons: list[NotificationButton]) -> None:
        await db.execute(
            "DELETE FROM notification_buttons WHERE notification_id = ?", (notif_id,)
        )
        for idx, btn in enumerate(buttons):
            await db.execute(
                """
                INSERT INTO notification_buttons (
                    notification_id, position, label, style, emoji,
                    ha_service, ha_entity_id, ha_data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notif_id, btn.position or idx, btn.label, btn.style, btn.emoji,
                    btn.ha_service, btn.ha_entity_id, btn.ha_data_json,
                ),
            )

    async def _replace_fields(self, db, notif_id: int, fields: list[NotificationField]) -> None:
        await db.execute(
            "DELETE FROM notification_fields WHERE notification_id = ?", (notif_id,)
        )
        for idx, fld in enumerate(fields):
            await db.execute(
                """
                INSERT INTO notification_fields (
                    notification_id, position, name, value_template, inline
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    notif_id, fld.position or idx, fld.name,
                    fld.value_template, int(fld.inline),
                ),
            )

    def _row_to_model(
        self,
        row,
        buttons: list[NotificationButton],
        fields: list[NotificationField],
    ) -> Notification:
        return Notification(
            id=row["id"],
            slug=row["slug"],
            channel_id=row["channel_id"],
            title=row["title"],
            message=row["message"],
            color=row["color"],
            icon_url=row["icon_url"],
            footer=row["footer"],
            show_timestamp=bool(row["show_timestamp"]),
            delete_button=bool(row["delete_button"]),
            snooze_button=bool(row["snooze_button"]),
            snooze_minutes=row["snooze_minutes"],
            buttons=buttons,
            fields=fields,
        )
