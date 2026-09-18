"""Verification du badge Cloudflare Access — port FastAPI / Starlette.

⚠️ MODULE PARTAGE : repris A L'IDENTIQUE de la logique testee du site-base
(socle-lite/ports/fastapi/cloudflare_access.py). Meme algorithme, memes garanties.
Le garder identique d'un site a l'autre permet de le synchroniser facilement.

Dependances : PyJWT[crypto].

⚠️ Ne jamais faire confiance a l'en-tete `Cf-Access-Authenticated-User-Email`
seul : on verifie le JWT `Cf-Access-Jwt-Assertion` (RS256) + `aud` + `iss`.
Et rendre l'origine injoignable hors Cloudflare (tunnel / pare-feu IP Cloudflare).
"""
from __future__ import annotations

try:
    import jwt
    from jwt import PyJWKClient
except Exception:  # PyJWT optionnel tant que la verif n'est pas active
    jwt = None
    PyJWKClient = None

# Cache des clients JWK, par equipe (la config peut changer).
_jwk_clients: dict = {}


def _normalize_team(raw: str) -> str:
    t = (raw or "").strip().lower()
    t = t.replace("https://", "").replace("http://", "").strip("/")
    return t.replace(".cloudflareaccess.com", "")


def _get_jwk_client(team: str):
    if not team or PyJWKClient is None:
        return None
    client = _jwk_clients.get(team)
    if client is None:
        client = PyJWKClient(f"https://{team}.cloudflareaccess.com/cdn-cgi/access/certs")
        _jwk_clients[team] = client
    return client


def cf_access_email(request, *, team: str, aud: str, verify: bool = True):
    """E-mail Cloudflare verifie pour la requete, sinon None.

    `request` : un objet Starlette/FastAPI `Request` (attributs `.headers`, `.cookies`).
    `team`    : nom de l'equipe Cloudflare (ex. « super-nono »).
    `aud`     : AUD de l'application Access.
    `verify`  : True en prod (verifie le JWT) ; False seulement en dev local.
    """
    # Starlette : en-tetes insensibles a la casse.
    header_email = request.headers.get("cf-access-authenticated-user-email")
    if not verify:
        return header_email.strip().lower() if header_email else None

    token = (request.headers.get("cf-access-jwt-assertion")
             or request.cookies.get("CF_Authorization"))
    if not token:
        return None

    team = _normalize_team(team)
    aud = (aud or "").strip()
    client = _get_jwk_client(team)
    if client is None or not aud or not team:
        return None

    try:
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"],
            audience=aud, issuer=f"https://{team}.cloudflareaccess.com",
        )
    except Exception:  # signature invalide, expire, aud/iss faux…
        return None

    email = (claims.get("email") or "").strip().lower()
    return email or None


def cf_access_email_verbose(request, *, team: str, aud: str):
    """Comme `cf_access_email` mais LEVE l'exception JWT (pour le diagnostic UI).

    Renvoie (email, None) si OK, sinon propage l'exception PyJWT afin d'afficher
    la vraie cause (audience, expiration, signature…). Enforcement : utiliser
    `cf_access_email` (qui, lui, renvoie None sans jamais lever).
    """
    token = (request.headers.get("cf-access-jwt-assertion")
             or request.cookies.get("CF_Authorization"))
    if not token:
        return None
    team = _normalize_team(team)
    aud = (aud or "").strip()
    client = _get_jwk_client(team)
    if client is None or not aud or not team:
        return None
    signing_key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token, signing_key.key, algorithms=["RS256"],
        audience=aud, issuer=f"https://{team}.cloudflareaccess.com",
    )
    email = (claims.get("email") or "").strip().lower()
    return email or None
