"""Route dashboard — statistiques aggregees pour la page d'accueil."""

from __future__ import annotations

from fastapi import APIRouter

from app.bot.client import bot
from app.db.repositories import LogRepository, NotificationRepository
from app.db.repositories.monitoring import MonitoringRepository
from app.ha import ha_client

router = APIRouter()


@router.get("/stats")
async def dashboard_stats() -> dict:
    """Retourne les stats consolidees pour la page d'accueil."""
    bot_ready = bot.is_ready()
    bot_latency = round(bot.latency * 1000, 1) if bot_ready else None

    ha_ok = await ha_client.ping()

    log_repo = LogRepository()
    today = await log_repo.stats_today()
    week_count = await log_repo.count_week()

    n_repo = NotificationRepository()
    notif_count = await n_repo.count_all()

    m_repo = MonitoringRepository()
    blocks = await m_repo.list_all()

    return {
        "bot_ready": bot_ready,
        "bot_latency_ms": bot_latency,
        "ha_ok": ha_ok,
        "sent_today": today["sent_ok"],
        "errors_today": today["sent_err"],
        "clicks_today": today["clicks"],
        "monitoring_total": len(blocks),
        "monitoring_enabled": sum(1 for b in blocks if b.enabled),
        "notifications_total": notif_count,
        "activity_week": week_count,
    }
