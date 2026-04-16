"""Point d'entree : lance le bot Discord et l'API FastAPI ensemble.

Tous deux tournent dans la meme event loop asyncio afin de partager
l'instance `bot` et le client HA.
"""

from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from app.api.server import app
from app.bot.client import start_bot, stop_bot
from app.config import settings
from app.db.database import init_db
from app.ha import ha_client

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_api() -> None:
    """Lance uvicorn dans la boucle courante (sans block)."""
    config = uvicorn.Config(
        app=app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)
    # Desactive la gestion des signaux par uvicorn (on la fait depuis main).
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    await server.serve()


async def _main() -> None:
    _configure_logging()
    await init_db()

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        logger.info("Signal recu, arret en cours...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows ne supporte pas add_signal_handler
            pass

    bot_task = asyncio.create_task(start_bot(), name="bot")
    api_task = asyncio.create_task(_run_api(), name="api")

    done, pending = await asyncio.wait(
        [bot_task, api_task, asyncio.create_task(stop_event.wait())],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Arret propre
    logger.info("Arret des services...")
    await stop_bot()
    await ha_client.close()
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
