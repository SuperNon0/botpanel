"""Authentification du panel : mots de passe hashes + sessions par cookie signe.

Aucune dependance externe : PBKDF2 (hashlib) pour les mots de passe et HMAC
(hmac) pour signer un cookie de session sans etat.

La protection est *activee* uniquement si un mot de passe admin est defini.
Sinon le panel reste ouvert (utile derriere Cloudflare Access ou en LAN).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from app.db.repositories import AuthRepository

COOKIE_NAME = "bp_session"
SESSION_TTL = 30 * 24 * 3600  # 30 jours
_PBKDF2_ROUNDS = 200_000


# ----------------------------------------------------------------------
# Mots de passe (PBKDF2-HMAC-SHA256)
# ----------------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Renvoie 'salt$hash' (hex)."""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, _ = stored.split("$", 1)
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored)


# ----------------------------------------------------------------------
# Sessions (cookie signe : payload.signature)
# ----------------------------------------------------------------------
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    return base64.urlsafe_b64decode(txt + "=" * (-len(txt) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(sig)


def create_session_token(username: str, secret: str, ttl: int = SESSION_TTL) -> str:
    payload = {"u": username, "exp": int(time.time()) + ttl}
    pb = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{pb}.{_sign(pb, secret)}"


def verify_session_token(token: str, secret: str) -> Optional[str]:
    """Renvoie le username si le token est valide et non expire, sinon None."""
    try:
        pb, sig = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(sig, _sign(pb, secret)):
        return None
    try:
        payload = json.loads(_b64d(pb))
        if int(payload["exp"]) < int(time.time()):
            return None
        return str(payload["u"])
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------
# Etat d'authentification (lu en base)
# ----------------------------------------------------------------------
async def auth_state() -> dict:
    """Renvoie {enabled, username, password_hash, secret}."""
    repo = AuthRepository()
    data = await repo.get()
    return {
        "enabled": bool(data["password_hash"]),
        "username": data["username"],
        "password_hash": data["password_hash"],
        "secret": data["session_secret"],
    }


async def current_user(request) -> Optional[str]:
    """Renvoie le username connecte via le cookie, ou None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    state = await auth_state()
    if not state["enabled"] or not state["secret"]:
        return None
    return verify_session_token(token, state["secret"])
