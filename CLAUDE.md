# CLAUDE.md — conventions du projet BotPanel

Instructions lues automatiquement par Claude Code à chaque session. À respecter
pour toute contribution.

## Règle : documentation à jour (IMPORTANTE)
- **À CHAQUE nouvelle fonctionnalité ou modification de comportement, mettre à
  jour le `README.md` dans le même changement** (section concernée : Sécurité,
  Fonctionnalités, Configuration, `.env`…). Une PR qui change le comportement
  sans toucher au README est incomplète.
- Mettre aussi à jour les docs concernées : `docs/CONNEXION.md` (auth),
  `.env.example` (nouvelle variable), `docs/V2-ROADMAP.md` (idée reportée en V2).
- Si un réglage devient configurable dans l'UI, le documenter (README + doc).

## Règle : futures nouveautés notées (IMPORTANTE)
- **Dès que l'utilisateur évoque ou décide une fonctionnalité future** (reportée,
  « pour plus tard », « pour la V2 »…), **la consigner dans `docs/V2-ROADMAP.md`**
  (quoi + pourquoi + décisions prises), pour ne rien perdre entre les sessions.
- Y sont déjà notés : intégration Home Assistant (notifications en entités +
  action avec autocomplétion, **sans pousser de valeurs depuis HA**), clé API
  (`X-API-Key`) sur `/api/notify` + webhooks (à faire avec l'HA), piste SSO
  Cloudflare centralisé pour la flotte.
- Quand une idée de la roadmap est implémentée, la **retirer de la roadmap** et la
  documenter dans le README.

## Sécurité (ne pas régresser)
- La vérif du badge Cloudflare vit dans `app/cloudflare_access.py` : **module
  partagé, repris à l'identique du socle `Site-base` (`claude/socle-lite`)**. Le
  garder synchronisé ; ne pas le diverger sans raison.
- Toujours vérifier le **JWT (RS256) + `aud` + `iss`** ; ne **jamais** faire
  confiance à l'en-tête `Cf-Access-Authenticated-User-Email` seul.
- Les **routes machine** (`/api/notify`, webhooks) restent **toujours ouvertes**
  (jamais derrière le login humain) — voir `_AUTH_PUBLIC_PREFIXES`.
- Mots de passe **hashés** (PBKDF2), jamais en clair.

## Workflow git
- Développer sur une **branche dédiée**, jamais directement sur `main`.
- Ne pas merger soi-même ni créer de PR sans demande explicite de l'utilisateur.

## Tests
- Vérifier au minimum : import de l'app (`create_app()`), et les garanties de
  sécurité (badge forgé rejeté, mode Cloudflare-only → 403, `/api/notify` ouvert).
- Dépendances : Python 3.11 ; installer `requirements.txt` **sans** `audioop-lts`
  (incompatible < 3.13).

## Stack (rappel)
FastAPI + uvicorn + discord.py dans une même boucle asyncio ; SQLite/aiosqlite ;
templates Jinja2 ; thème « RecipeLog » (accent doré `#e8c547`, DM Serif + DM Mono).
