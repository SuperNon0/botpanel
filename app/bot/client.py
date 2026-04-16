"""Instance du bot Discord + boot."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from app.config import settings

logger = logging.getLogger(__name__)


intents = discord.Intents.default()
intents.message_content = False  # pas besoin, on n'ecoute pas les messages


class BotPanelBot(commands.Bot):
    """Bot Discord BotPanel.

    Le re-enregistrement des vues persistantes et la sync des slash commands
    sont faits dans `setup_hook` pour etre pret des la connexion.
    """

    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self) -> None:
        # Import tardif pour eviter les cycles.
        from app.bot.views import register_persistent_views
        from app.bot.slash_sync import sync_slash_commands
        from app.bot.monitoring import start_monitoring_tasks

        await register_persistent_views(self)
        await sync_slash_commands(self)
        await start_monitoring_tasks(self)

    async def on_ready(self) -> None:
        logger.info("Bot connecte : %s (id=%s)", self.user, self.user.id if self.user else "?")


bot = BotPanelBot()


async def start_bot() -> None:
    """Lance la connexion Discord (appele depuis main.py)."""
    await bot.start(settings.discord_token)


async def stop_bot() -> None:
    if not bot.is_closed():
        await bot.close()
