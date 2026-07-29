"""Reinitialisation du mot de passe admin (secours en cas d'oubli).

Usage :
    python -m app.reset_admin              # supprime le mot de passe -> panel ouvert
    python -m app.reset_admin "nouveau"    # definit un nouveau mot de passe

Apres execution, redemarre le service (sudo systemctl restart botpanel).
"""

from __future__ import annotations

import asyncio
import sys

from app.auth import hash_password
from app.db.database import init_db
from app.db.repositories import AuthRepository


async def _run() -> None:
    await init_db()
    repo = AuthRepository()
    new_password = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    if new_password:
        await repo.set_password(hash_password(new_password))
        print("Mot de passe admin redefini. Connecte-toi avec ce nouveau mot de passe.")
    else:
        await repo.clear_password()
        print(
            "Mot de passe admin supprime : le panel est de nouveau ouvert.\n"
            "Redefinis-en un dans Parametres > Compte & securite."
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
