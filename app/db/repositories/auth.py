"""Repository du compte admin (authentification du panel).

Table `admin_auth` a une seule ligne (id = 1) :
- password_hash NULL  -> protection desactivee (panel ouvert)
- password_hash defini -> login requis pour les pages web
- session_secret       -> cle de signature des cookies de session
"""

from __future__ import annotations

import secrets
from typing import Optional

from app.db.database import get_connection


class AuthRepository:
    """Acces au compte admin unique."""

    async def _ensure_row(self, db) -> None:
        await db.execute(
            "INSERT OR IGNORE INTO admin_auth (id, username) VALUES (1, 'admin')"
        )

    async def get(self) -> dict:
        """Renvoie {username, password_hash, session_secret}."""
        async with get_connection() as db:
            await self._ensure_row(db)
            await db.commit()
            cursor = await db.execute(
                "SELECT username, password_hash, session_secret FROM admin_auth WHERE id = 1"
            )
            row = await cursor.fetchone()
            return {
                "username": row["username"] if row else "admin",
                "password_hash": row["password_hash"] if row else None,
                "session_secret": row["session_secret"] if row else None,
            }

    async def get_or_create_secret(self, password_hash: str) -> Optional[str]:
        """Amorce une ancienne ligne sans secret sans rétablir une session révoquée."""
        async with get_connection() as db:
            cursor = await db.execute(
                "UPDATE admin_auth SET session_secret = COALESCE(session_secret, ?) "
                "WHERE id = 1 AND password_hash = ? RETURNING session_secret",
                (secrets.token_hex(32), password_hash),
            )
            row = await cursor.fetchone()
            await cursor.close()
            await db.commit()
            return row["session_secret"] if row else None

    async def set_password(self, password_hash: str, username: Optional[str] = None) -> str:
        """Change le mot de passe et révoque toutes les anciennes sessions."""
        secret = secrets.token_hex(32)
        async with get_connection() as db:
            await self._ensure_row(db)
            await db.execute(
                "UPDATE admin_auth SET password_hash = ?, username = COALESCE(?, username), "
                "session_secret = ?, updated_at = datetime('now') WHERE id = 1",
                (password_hash, username, secret),
            )
            await db.commit()
        return secret

    async def clear_password(self) -> None:
        """Supprime le mot de passe (desactive la protection) et regenere le secret
        pour invalider toutes les sessions en cours."""
        async with get_connection() as db:
            await self._ensure_row(db)
            await db.execute(
                "UPDATE admin_auth SET password_hash = NULL, session_secret = ?, updated_at = datetime('now') WHERE id = 1",
                (secrets.token_hex(32),),
            )
            await db.commit()
