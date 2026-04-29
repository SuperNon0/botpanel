"""Lecture de l'historique des notifications/clics."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.db.models import NotificationLog
from app.db.repositories import LogRepository

router = APIRouter()
repo = LogRepository()


@router.get("", response_model=list[NotificationLog])
async def list_logs(
    limit: int = Query(200, ge=1, le=1000),
    kind: Optional[str] = None,
    notification_id: Optional[int] = None,
) -> list[NotificationLog]:
    return await repo.list_recent(
        limit=limit, kind=kind, notification_id=notification_id,
    )


@router.delete("/older/{days}")
async def purge(days: int) -> dict[str, int]:
    n = await repo.purge_older_than(days)
    return {"deleted": n}
