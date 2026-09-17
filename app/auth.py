"""Authentification du panel : mots de passe hashes + sessions par cookie signe.

Aucune dependance externe : PBKDF2 (hashlib) pour les mots de passe et HMAC
(hmac) pour signer un cookie de session sans etat.

La protection est *activee* uniquement si un mot de passe admin est defini.
Sinon le panel reste ouvert (utile derriere Cloudflare Access ou en LAN).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from app.config import settings as app_settings
from app.db.repositories import AuthRepository, SettingsRepository

# PyJWT est optionnel au demarrage : on n'exige la lib que si la verif est active.
try:
    import jwt as _jwt
    from jwt import PyJWKClient as _PyJWKClient
except Exception:  # pragma: no cover
    _jwt = None
    _PyJWKClient = None

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


# ----------------------------------------------------------------------
# Cloudflare Access (le "badge") — deuxieme porte d'entree
# ----------------------------------------------------------------------
# Principe (cf. Site-base) : Cloudflare ajoute a la requete un JETON SIGNE
# (`Cf-Access-Jwt-Assertion`). On verifie sa signature (RS256) + l'audience (aud)
# + l'emetteur (iss). Un simple en-tete `Cf-Access-Authenticated-User-Email` est
# FALSIFIABLE en local : on ne s'y fie jamais quand la verif est active.
_jwk_clients: dict = {}


def normalize_team(team: str) -> str:
    """Garde le NOM d'equipe seul (ex. 'super-nono'), quelle que soit la saisie."""
    t = (team or "").strip().lower()
    t = t.removeprefix("https://").removeprefix("http://").strip("/")
    t = t.removesuffix(".cloudflareaccess.com")
    return t.strip("/")


async def cf_config() -> dict:
    """Config Cloudflare effective : reglages UI (table settings) prioritaires, sinon .env."""
    repo = SettingsRepository()
    team = await repo.get("cf_team", None)
    if team is None:
        team = app_settings.cf_access_team_domain
    aud = await repo.get("cf_aud", None)
    if aud is None:
        aud = app_settings.cf_access_aud
    verify = await repo.get("cf_verify", None)
    if verify is None:
        verify = bool(app_settings.cf_verify_jwt)
    return {"team": normalize_team(team or ""), "aud": (aud or "").strip(), "verify": bool(verify)}


def _cf_token(request) -> Optional[str]:
    return (request.headers.get("cf-access-jwt-assertion")
            or request.cookies.get("CF_Authorization"))


def _get_jwk_client(team: str):
    if not team or _PyJWKClient is None:
        return None
    client = _jwk_clients.get(team)
    if client is None:
        client = _PyJWKClient(f"https://{team}.cloudflareaccess.com/cdn-cgi/access/certs")
        _jwk_clients[team] = client
    return client


def _verify_cf_token_sync(token: str, team: str, aud: str) -> Optional[str]:
    """Verifie le JWT (BLOQUANT : recupere les cles Cloudflare). Via asyncio.to_thread."""
    if _jwt is None:
        return None
    client = _get_jwk_client(team)
    if client is None:
        return None
    signing_key = client.get_signing_key_from_jwt(token)
    claims = _jwt.decode(
        token, signing_key.key, algorithms=["RS256"],
        audience=aud, issuer=f"https://{team}.cloudflareaccess.com",
    )
    email = (claims.get("email") or "").strip().lower()
    return email or None


async def cf_access_email(request) -> Optional[str]:
    """E-mail Cloudflare VERIFIE pour la requete, sinon None.

    - verify=True (defaut) : valide le JWT (signature + aud + iss). Un en-tete
      forge sans JWT valide est IGNORE -> pas d'usurpation possible en local.
    - verify=False : se contente de l'en-tete (dev uniquement).
    """
    cfg = await cf_config()
    header_email = request.headers.get("cf-access-authenticated-user-email")
    if not cfg["verify"]:
        return header_email.strip().lower() if header_email else None
    token = _cf_token(request)
    if not token or not cfg["team"] or not cfg["aud"] or _jwt is None:
        return None
    try:
        return await asyncio.to_thread(_verify_cf_token_sync, token, cfg["team"], cfg["aud"])
    except Exception:  # noqa: BLE001 — token invalide/expire/aud faux…
        return None


async def cf_diagnostic(request, team: Optional[str] = None, aud: Optional[str] = None) -> dict:
    """Diagnostic Cloudflare (pour la carte Parametres / bouton Tester)."""
    cfg = await cf_config()
    if team is not None:
        cfg = {
            "team": normalize_team(team),
            "aud": (aud if aud is not None else cfg["aud"]) or cfg["aud"],
            "verify": cfg["verify"],
        }
    header_email = request.headers.get("cf-access-authenticated-user-email")
    token = _cf_token(request)
    d = {
        "team": cfg["team"], "aud": cfg["aud"], "verify": cfg["verify"],
        "header_email": header_email, "has_token": bool(token),
        "jwt_status": "non teste", "jwt_email": None, "jwt_error": None,
    }
    if not token:
        d["jwt_error"] = "Aucun jeton Cloudflare recu (l'origine n'est peut-etre pas derriere Access)."
        return d
    if not cfg["team"] or not cfg["aud"]:
        d["jwt_error"] = "Equipe et/ou AUD non renseignes."
        return d
    if _jwt is None:
        d["jwt_error"] = "PyJWT indisponible."
        return d
    try:
        email = await asyncio.to_thread(_verify_cf_token_sync, token, cfg["team"], cfg["aud"])
        d["jwt_status"] = "OK ✓"
        d["jwt_email"] = email
    except Exception as exc:  # noqa: BLE001
        d["jwt_status"] = "echec ✗"
        d["jwt_error"] = str(exc)
    return d


async def is_authenticated(request) -> Optional[dict]:
    """Renvoie {method, email/username} si la requete est authentifiee, sinon None.

    Deux portes : badge Cloudflare verifie, ou session mot de passe (LAN).
    """
    email = None
    try:
        email = await cf_access_email(request)
    except Exception:  # noqa: BLE001
        email = None
    if email:
        return {"method": "cloudflare", "email": email, "username": None}
    user = await current_user(request)
    if user:
        return {"method": "password", "email": None, "username": user}
    return None
