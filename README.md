<p align="center">
  <img src="app/web/static/favicon.svg" width="96" alt="BotPanel">
</p>

<h1 align="center">BotPanel</h1>

Bot Discord × Home Assistant, administré depuis un site web dédié.  
Hébergé dans un conteneur LXC Proxmox.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![discord.py 2.4](https://img.shields.io/badge/discord.py-2.4-5865F2)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)

## Fonctionnalités

- **Notifications Discord** configurables depuis le site — HA n'a qu'un seul appel à faire (`rest_command.bot_discord` avec `id: <slug>`)
- **Trois modes d'envoi** par notification : *Direct* (channel texte), *Thread* (fil dans un channel texte, regroupé par groupe), *Forum* (post dans un channel forum Discord)
- **Boutons interactifs** (persistants, survivent au timeout 15 min et aux redémarrages) : Supprimer, Snooze, boutons custom appelant un service HA
- **Commandes slash Discord** : deux commandes fixes (`/ha`, `/clear`) + commandes personnalisées entièrement gérées depuis le site (service / script / scène / notification)
- **Monitoring temps réel** : messages épinglés édités à intervalle configurable (min. 30 s), recréés automatiquement si supprimés côté Discord
- **Templates dans les champs** : syntaxe BotPanel (`{state:sensor.x}`, `{attr:sensor.x:attr}`, `{unit:sensor.x}`) et Jinja HA natif (`{{ states('...') }}`, `{{ state_attr(...) }}`)
- **Texte dynamique via l'API** : variables `{var:nom}` (avec valeur par défaut `{var:nom|défaut}`) remplies par n'importe quel projet — voir [docs/API.md](docs/API.md)
- **Images** : miniature (petite) et **grande image** (affiche), toutes deux compatibles avec les variables — idéal pour une affiche de film/série envoyée dynamiquement (Sonarr, Radarr…)
- **Autocomplétion live** des entités HA, services HA et channels Discord dans tous les formulaires
- **Page Paramètres** : presets de couleurs et de channels, liste des forums détectés, gestion des threads/posts actifs, mise à jour et redémarrage depuis l'UI
- **Page Historique** : logs de tous les envois et clics de boutons, avec **origine de l'envoi** (Home Assistant / Proxmox / API / Manuel / Test), filtre et purge
- **Intégration Home Assistant native** : composant HA officiel (boutons par notification, action `botpanel.envoyer`, capteurs d'état), sécurisé par une clé API
- **Intégration Proxmox VE / PBS** : les backups/sync envoient leurs notifs directement à BotPanel (webhook natif), avec variables `{var:...}` et couleur auto selon le statut
- **Aide contextuelle** : des petits « ? » partout ouvrent une pop-up d'explication (fini la page Aide séparée)
- **Aperçu live avec vraies valeurs HA** : l'éditeur de notification résout `{state:...}`/`{attr:...}`/Jinja avec les valeurs réelles récupérées en direct
- **Authentification à deux portes** : mot de passe local (LAN) + badge Cloudflare Access vérifié (JWT), avec mode « Cloudflare uniquement »
- **PWA installable** + interface animée (respecte « réduire les animations »), squelettes de chargement, états vides illustrés
- **Design FuelLog** (dark mode exclusif, DM Mono + DM Serif Display)

## Le site web

Le site est l'interface d'administration du bot, accessible sur `http://IP_LXC:8080`. Il regroupe plusieurs sections : Accueil, Notifications, Commandes, Monitoring, Historique et Paramètres.

> **Aide contextuelle** : partout où c'est utile, un petit **« ? »** ouvre une pop-up d'explication (slug, mode d'envoi, placeholders, clé API, Cloudflare, sauvegarde…), avec encadrés colorés et blocs de code copiables. Plus besoin d'une page Aide séparée (l'ancienne reste accessible sur `/aide` en secours).

> **Interface animée** : micro-interactions et animations d'entrée légères (survol des cartes, retour au clic des boutons, focus clavier visible, toasts, `skeleton`/`spinner` de chargement) via `static/css/animations.css` + `static/js/anim.js`. Le tout est **additif** (ne change pas la mise en page) et **respecte `prefers-reduced-motion`** : si l'utilisateur a demandé à réduire les animations (OS/navigateur), elles sont automatiquement désactivées.
>
> **Squelettes de chargement** : les listes (notifications, commandes, monitoring, historique) affichent des blocs animés (`data-skeleton`) le temps que les données arrivent, au lieu d'une zone blanche.
>
> **États vides illustrés** : quand une liste est vide, un écran avec icône + message + bouton d'action s'affiche (au lieu d'un simple texte).
>
> **PWA installable** : BotPanel peut être **ajouté à l'écran d'accueil** (mobile/desktop) et s'ouvre en plein écran comme une app. Fourni par `manifest.webmanifest` + `sw.js` (service worker, servis à la racine) et les icônes `static/icons/`. Le service worker fait du **network-first** avec repli hors-ligne et **ne met jamais en cache les appels `/api/`** (données live / webhooks machines).

### Notifications (`/notifications`)

Page principale. Elle liste toutes les notifications enregistrées, **groupées par leur groupe** (le champ « rangement sur le site », indépendant de Discord) si défini. Pour chaque notification on peut : tester l'envoi, éditer, cloner ou supprimer.

Le formulaire d'édition permet de configurer :
- **Identification** : slug, channel Discord cible, **mode d'envoi** (Direct / Thread / Forum) et nom de groupe/post selon le mode
- **Embed** : titre, message (Markdown), couleur (sélecteur + presets), icône, footer, horodatage
- **Boutons** : cases "Supprimer" et "Snooze N min", plus des boutons custom déclenchant un service HA au clic
- **Champs** : fields Discord affichés en grille dans l'embed, avec templates d'états HA

Un **aperçu live** du rendu Discord est affiché pendant l'édition. Un bouton "Tester" envoie la notification dans Discord sans sauvegarder.

> **Aperçu avec vraies valeurs Home Assistant** : l'aperçu résout en direct les placeholders HA (`{state:...}`, `{attr:...}`, `{unit:...}`, Jinja HA) avec les **valeurs réelles** récupérées depuis Home Assistant (endpoint `POST /api/notifications/resolve-preview`, sans rien envoyer sur Discord). Un voyant indique l'état (🟢 valeurs en direct / 🔴 HA injoignable) et un bouton **« 🔄 Valeurs HA »** rafraîchit. Les `{var:...}` (remplis au déclenchement) restent affichés tels quels. Le bouton **« + entité »** de la barre d'outils insère l'entité choisie sous forme `{state:...|--}`.

### Commandes (`/commands`)

Gestion des commandes slash personnalisées. Chaque commande a :
- un **nom** (identifiant Discord, lettres minuscules/chiffres/tirets, max 32 car.)
- une **description** affichée dans Discord
- un **type d'action** : service HA, script, scène, ou notification BotPanel
- un **message de confirmation** éphémère envoyé à l'utilisateur après exécution

Un compteur de quota affiche le nombre de commandes utilisées sur les 100 autorisées par Discord.

### Monitoring (`/monitoring`)

Gestion des blocs de monitoring — des messages épinglés qui se mettent à jour automatiquement dans un channel Discord à intervalle régulier.

Chaque bloc expose :
- un **nom**, une **couleur** et une **icône**
- le **channel Discord** cible et l'**intervalle de rafraîchissement** (min. 30 s)
- une liste de **champs** pointant vers des entités HA (état, attribut, suffix, inline)

Le bot crée le message épinglé au premier cycle et ne fait que l'éditer ensuite. Si le message est supprimé manuellement sur Discord, il est recréé au cycle suivant.

### Paramètres (`/settings`)

- **Mise à jour** : affiche la branche et le commit git courants ; un bouton lance un `git pull` + réinstallation des dépendances + redémarrage automatique du service (la page se recharge quand le bot revient)
- **Couleurs préconfigurées** : palette de couleurs nommées disponibles dans le sélecteur rapide du formulaire notification
- **Channels Discord préconfigurés** : liste de channels avec leurs IDs, affichés dans la liste déroulante du formulaire ; un tableau des channels détectés par le bot permet de les ajouter en un clic
- **Channels forum détectés** : liste des channels forum accessibles par le bot, utilisables comme destination en mode *Forum*
- **Threads / Posts actifs** : liste tous les fils et posts créés automatiquement ; bouton "Réinitialiser" par entrée pour forcer la recréation au prochain envoi
- **Sauvegarde & migration** : export/import JSON de toute la configuration
- **Compte & sécurité** : activer/changer/désactiver le mot de passe admin (LAN)
- **Cloudflare / Accès** : équipe + AUD + bouton **Tester**, et l'option « accès uniquement Cloudflare »
- **API / Intégration** : clé API (copier / régénérer) pour le composant Home Assistant + diagnostic « l'intégration marche ? »

### Historique (`/historique`)

Journal de toutes les activités du bot : envois de notifications, clics sur les boutons (Supprimer, Snooze, action HA). Chaque entrée indique la notification concernée, l'**origine de l'envoi** (🏠 Home Assistant / API / Manuel / Test), l'utilisateur (pour les clics), le channel, l'horodatage et si l'opération a réussi. Filtrable et purgeable.

## Commandes slash Discord

### `/ha` — appel libre de service HA

Permet d'appeler n'importe quel service Home Assistant directement depuis Discord.

| Paramètre | Requis | Description |
|-----------|--------|-------------|
| `service` | oui | Service HA au format `domain.action` (ex : `light.turn_on`) |
| `entity` | non | Entity ID cible (ex : `light.salon`) |
| `data` | non | Payload JSON additionnel (ex : `{"brightness": 200}`) |

L'autocomplétion est intelligente : les domaines courants (`light`, `switch`, `script`, `scene`…) apparaissent en tête quand le champ est vide ; la liste des entités se filtre automatiquement selon le domaine du service choisi.

### `/clear` — suppression de messages

Supprime les N derniers messages du channel courant (1 à 1000).  
Nécessite la permission `Manage Messages` côté utilisateur **et** côté bot.

### Commandes personnalisées

Créées et gérées depuis `/commands` sur le site. Elles sont synchronisées sur la guild instantanément à chaque modification. Quatre types d'action disponibles :

| Type | Comportement |
|------|-------------|
| `service` | Appelle `domain.action` avec entity et data optionnels |
| `script` | Exécute un script HA (`script.<nom>`) |
| `scene` | Active une scène HA (`scene.turn_on`) |
| `notification` | Envoie une notification BotPanel par son slug |

> Les noms `ha` et `clear` sont réservés et ne peuvent pas être utilisés pour des commandes personnalisées.

## Architecture

```
app/
├── main.py              # Lance bot + API dans la même event loop asyncio
├── config.py            # Pydantic Settings (lit .env)
├── auth.py              # Mots de passe (PBKDF2) + sessions + config Cloudflare
├── cloudflare_access.py # Vérif du badge Cloudflare (JWT) — partagé avec Site-base
├── integration.py       # Clé API machine (X-API-Key) pour l'intégration HA
├── db/
│   ├── database.py      # SQLite async (aiosqlite)
│   ├── models.py        # Schémas Pydantic
│   └── repositories/    # Accès données par entité
│       ├── notifications.py
│       ├── slash_commands.py
│       ├── monitoring.py
│       ├── threads.py
│       ├── logs.py
│       └── settings.py
├── bot/                 # discord.py : client, notifications, views, slash, monitoring
├── ha/                  # Client httpx pour l'API HA
├── api/
│   ├── server.py        # Instanciation FastAPI + montage des routeurs
│   └── routes/          # Un fichier par groupe de routes
└── web/
    ├── templates/        # Templates Jinja2
    └── static/           # CSS + JS + icônes PWA

custom_components/botpanel/   # Composant Home Assistant (HACS) : boutons, capteurs, action
hacs.json                     # Métadonnées HACS
```

## Intégrer un projet (API notifications)

N'importe quel projet peut déclencher une notification Discord via une simple
requête HTTP. Tu crées la notification une fois dans le panel (avec un **slug**),
et ton projet envoie ce slug :

```bash
curl -X POST http://IP_BOTPANEL:8080/api/notify \
  -H "Content-Type: application/json" \
  -d '{"id": "mon_slug"}'
```

Cette route reste **toujours accessible** (même avec la protection par mot de passe
activée), pour ne jamais bloquer tes intégrations.

👉 **Guide complet avec exemples (Python, Node.js, PHP, Bash, Home Assistant) :
[docs/API.md](docs/API.md)**

## Endpoints

### API REST

| Méthode | Route | Usage |
|---------|-------|-------|
| `POST` | `/api/notify` | Déclenche une notification — `{"id": "<slug>"}` (HA ou tout projet, voir [docs/API.md](docs/API.md)) |
| `GET` | `/api/notifications` | Liste toutes les notifications |
| `POST` | `/api/notifications` | Crée une notification |
| `GET` | `/api/notifications/{id}` | Détail d'une notification |
| `PUT` | `/api/notifications/{id}` | Modifie une notification |
| `DELETE` | `/api/notifications/{id}` | Supprime une notification |
| `POST` | `/api/notifications/{id}/test` | Envoie la notification en test |
| `POST` | `/api/notifications/{id}/duplicate` | Duplique (slug `<original>_copy`) |
| `POST` | `/api/notifications/preview` | Prévisualise sans sauvegarder |
| `POST` | `/api/notifications/resolve-preview` | Résout les placeholders HA d'un brouillon (valeurs réelles, sans envoi) |
| `GET` | `/api/commands` | Liste les commandes slash |
| `POST` | `/api/commands` | Crée une commande slash |
| `PUT` | `/api/commands/{id}` | Modifie une commande slash |
| `DELETE` | `/api/commands/{id}` | Supprime une commande slash |
| `GET` | `/api/commands/quota` | Quota Discord (max 100) |
| `GET` | `/api/monitoring` | Liste les blocs de monitoring |
| `POST` | `/api/monitoring` | Crée un bloc |
| `PUT` | `/api/monitoring/{id}` | Modifie un bloc |
| `DELETE` | `/api/monitoring/{id}` | Supprime un bloc |
| `GET` | `/api/ha/entities?domain=light` | Entités HA (autocomplétion, filtrable par domaine) |
| `GET` | `/api/ha/services` | Services HA (autocomplétion) |
| `GET` | `/api/ha/ping` | Vérifie la connectivité avec HA |
| `GET` | `/api/discord/channels` | Channels texte de la guild (autocomplétion) |
| `GET` | `/api/discord/forum-channels` | Channels forum de la guild |
| `GET` | `/api/discord/forum-posts?channel_id=X` | Posts actifs d'un channel forum |
| `GET` | `/api/settings/colors` | Presets de couleurs sauvegardés |
| `PUT` | `/api/settings/colors` | Enregistre les presets de couleurs |
| `GET` | `/api/settings/channels` | Presets de channels sauvegardés |
| `PUT` | `/api/settings/channels` | Enregistre les presets de channels |
| `GET` | `/api/settings/threads` | Liste les threads Discord actifs |
| `DELETE` | `/api/settings/threads/{id}` | Réinitialise un thread (recréé au prochain envoi) |
| `GET` | `/api/logs` | Historique des envois et clics (filtres : `limit`, `kind`, `notification_id`) |
| `DELETE` | `/api/logs/older/{days}` | Purge les logs de plus de N jours |
| `GET` | `/api/system/info` | Infos système (commit et branche git courants) |
| `POST` | `/api/system/update` | `git fetch && git pull --ff-only` |
| `POST` | `/api/system/restart` | `systemctl restart botpanel` (détaché) |
| `GET` | `/api/settings/integration` | État de l'intégration (clé API, HA joignable, dernière connexion) |
| `POST` | `/api/settings/integration/regenerate` | Régénère la clé API |
| `GET` | `/health` | Vérification de santé — `{"status": "ok"}` |
| `GET` | `/api/docs` | Documentation Swagger UI |

#### Authentification (`/api/auth/*`)

| Méthode | Route | Usage |
|---------|-------|-------|
| `GET` | `/api/auth/me` | État de connexion (méthode Cloudflare / mot de passe) |
| `POST` | `/api/auth/login` · `/logout` | Connexion / déconnexion (mot de passe LAN) |
| `POST` | `/api/auth/password` · `/disable` | Définir/changer · désactiver le mot de passe |
| `GET`/`POST` | `/api/auth/cf-config` | Lire / enregistrer la config Cloudflare (équipe, AUD, verify, allow_local) |
| `POST` | `/api/auth/cf-test` | Diagnostic du badge Cloudflare |

#### Intégration machine (`/api/integration/*`, clé `X-API-Key` requise)

| Méthode | Route | Usage |
|---------|-------|-------|
| `GET` | `/api/integration/ping` | Identité + version (validation config HA) |
| `GET` | `/api/integration/notifications` | Liste compacte des notifications (boutons/action) |
| `GET` | `/api/integration/state` | Capteurs : bot en ligne, envois jour/total, nb notifs, dernière alerte |
| `POST` | `/api/integration/trigger` | Déclenche une notification par `id`/`slug` (origine = home_assistant) |
| `POST` | `/api/integration/proxmox/{slug}` | Webhook Proxmox/PBS → déclenche la notif `slug` (parse le message en `{var:...}`) |

#### PWA

| Méthode | Route | Usage |
|---------|-------|-------|
| `GET` | `/manifest.webmanifest` | Manifest PWA (installable) |
| `GET` | `/sw.js` | Service worker (repli hors-ligne, ne cache jamais `/api/`) |

### Pages web

| Route | Page |
|-------|------|
| `/dashboard` | Accueil : statut du bot/HA + statistiques |
| `/notifications` | Liste des notifications (groupées par groupe) |
| `/notifications/new` | Créer une notification |
| `/notifications/{id}` | Éditer une notification |
| `/commands` | Liste des commandes slash + quota |
| `/commands/new` | Créer une commande |
| `/commands/{id}` | Éditer une commande |
| `/monitoring` | Liste des blocs de monitoring |
| `/monitoring/new` | Créer un bloc |
| `/monitoring/{id}` | Éditer un bloc |
| `/settings` | Paramètres (presets, sécurité, Cloudflare, intégration, mise à jour…) |
| `/historique` | Historique des envois (avec origine) et clics de boutons |
| `/aide` | Page d'aide (modes d'envoi, placeholders, tutoriel Discord) |
| `/login` · `/login/forgot` | Connexion locale · réinitialisation du mot de passe |

## Installation (LXC Proxmox)

### 1. Créer le conteneur

- Template : Debian 12 ou Ubuntu 22.04
- Ressources : 1 vCPU, 512 Mo RAM, 4 Go stockage

### 2. Installer BotPanel

```bash
# Dans le conteneur
apt update && apt install -y git
git clone https://github.com/<user>/botpanel.git /opt/botpanel
cd /opt/botpanel
sudo bash deploy/install_lxc.sh
```

Le script effectue automatiquement :
- Installation des dépendances système et du venv Python
- Création de l'utilisateur système `botpanel`
- Copie et activation du service systemd
- Configuration du sudoers pour le redémarrage depuis l'UI (sans mot de passe)

### 3. Configurer le fichier `.env`

```bash
sudo nano /opt/botpanel/.env
```

Remplir :
- `DISCORD_TOKEN` — token du bot Discord
- `DISCORD_GUILD_ID` — ID du serveur
- `DISCORD_DEFAULT_CHANNEL_ID` — channel par défaut des notifications
- `DISCORD_MONITORING_CHANNEL_ID` — channel du monitoring
- `HA_BASE_URL` — `http://IP_HA:8123`
- `HA_TOKEN` — token longue durée HA

Variables **optionnelles** (sinon gérées depuis les Paramètres) : `ADMIN_PASSWORD`, `CF_ACCESS_TEAM_DOMAIN`, `CF_ACCESS_AUD`, `CF_VERIFY_JWT`, `ALLOW_LOCAL_LOGIN`, `INTEGRATION_API_KEY` — voir [`.env.example`](.env.example).

### 4. Démarrer

```bash
sudo systemctl start botpanel
sudo journalctl -u botpanel -f   # suivre les logs
```

Le site est accessible sur `http://IP_LXC:8080`.

### 5. Cloudflare Tunnel (optionnel)

Le site peut être exposé via Cloudflare Zero Trust (authentification SSO).  
Configurer un tunnel pointant vers `http://IP_LXC:8080` et activer la politique d'accès.

## Configuration Home Assistant

Deux façons de connecter Home Assistant :
- **Méthode simple (ci-dessous)** : un `rest_command` qui appelle `/api/notify`. Rapide, sans installation dans HA.
- **Composant natif (recommandé)** : boutons + action + capteurs dans HA — voir [Intégration Home Assistant](#intégration-home-assistant-composant-natif).

Ajouter dans `configuration.yaml` :

```yaml
rest_command:
  bot_discord:
    url: "http://IP_LXC:8080/api/notify"
    method: POST
    content_type: "application/json"
    payload: '{"id": "{{ id }}"}'
    timeout: 10
```

Puis dans une automation :

```yaml
action:
  - service: rest_command.bot_discord
    data:
      id: "notif_porte_entree"
```

## Stack

| Composant | Techno |
|-----------|--------|
| Langage | Python 3.11+ |
| Bot | discord.py 2.4 |
| API / Web | FastAPI 0.115 + Uvicorn 0.30 |
| DB | SQLite via aiosqlite 0.20 |
| HTTP client | httpx 0.27 |
| Config | pydantic-settings 2.5 |
| Templates | Jinja2 3.1 |
| Auth Cloudflare | PyJWT 2.9 + cryptography 43 (vérif JWT du badge) |
| Intégration HA | Composant Home Assistant (config flow + DataUpdateCoordinator) |
| Conteneur | LXC Proxmox + systemd |

## Points d'attention

- **Boutons Discord** : les `custom_id` sont de la forme `bp:<action>:<notif_id>[:<btn_id>]` (actions : `del`, `snz`, `btn`, `preview`). Un dispatcher global (`on_interaction`) route les clics — aucun besoin de reconstruire les Views au boot.
- **Modes d'envoi** : `thread_mode` sur chaque notification — `none` (direct), `thread` (fil dans channel texte), `forum` (post dans channel forum). Les tests et previews depuis l'éditeur ignorent toujours le mode et vont dans le channel direct. Le `thread_id`/`post_id` est stocké en DB par `(group_name, channel_id)` ; si archivé → désarchivé, si supprimé → recréé automatiquement. En mode forum, si le post n'est pas en DB, le bot le cherche par nom dans les posts actifs avant d'en créer un nouveau.
- **Token HA** : créer un token avec uniquement les permissions nécessaires (lecture états + appel services).
- **Sync slash** : les commandes sont poussées sur la **guild** (pas en global) → propagation immédiate. Les noms `ha` et `clear` sont réservés.
- **Monitoring** : chaque bloc garde l'ID du message épinglé en DB. Si le message a été supprimé côté Discord, il est recréé au cycle suivant. Intervalle minimum : 30 secondes.
- **Redémarrage depuis l'UI** : `POST /api/system/restart` lance le restart en tâche détachée. L'API devient inaccessible quelques secondes ; le frontend poll `/health` pour détecter le retour.
- **Mise à jour depuis l'UI** : `POST /api/system/update` effectue un `git pull --ff-only`. Le sudoers est configuré automatiquement par `install_lxc.sh` — aucune manipulation manuelle nécessaire.

## Premier lancement — assistant de configuration

Au tout premier démarrage, si le fichier `.env` est absent ou incomplet, BotPanel démarre en **mode configuration** : ouvre `http://IP:8080` et un **assistant** te demande toutes les informations (token Discord, IDs de serveur/channels, URL + token Home Assistant). Tu remplis, tu cliques **Enregistrer et démarrer** : le `.env` est écrit automatiquement et le service redémarre tout seul. **Aucune édition de fichier en SSH n'est nécessaire.**

Les appels machine (`/api/notify`, etc.) ne sont jamais bloqués par ce mode.

## Sauvegarde & migration (export / import)

Depuis **Paramètres → Sauvegarde & migration** :
- **Exporter** : télécharge un fichier JSON contenant toutes tes données de configuration (notifications, commandes, monitoring, paramètres).
- **Importer** : recharge ce fichier sur une **nouvelle instance** (ou pour restaurer). ⚠️ L'import remplace les données de configuration existantes. L'historique et les états Discord (threads/posts) ne sont pas concernés.

## Sécurité et accès

BotPanel intègre une **authentification à deux portes** (voir [docs/CONNEXION.md](docs/CONNEXION.md)). Elle est **additive** : inerte tant que rien n'est configuré (panel ouvert en LAN), activable quand tu veux.

- **En local (LAN)** : mot de passe admin — **un seul champ, aucun identifiant** (Paramètres → Compte & sécurité). Réinitialisable sur le serveur (`deploy/reset_admin.sh`).
- **Via Cloudflare Access** : connexion automatique **sans mot de passe** — BotPanel **vérifie le badge signé** (JWT **RS256 + `aud` + `iss`**), donc **pas d'usurpation possible** en local (l'en-tête `Cf-Access-Authenticated-User-Email` seul n'est jamais cru). Configurable dans **Paramètres → Cloudflare / Accès** (équipe, AUD, bouton **Tester**).
- **Mode « Cloudflare uniquement »** (`ALLOW_LOCAL_LOGIN=false`, ou la case dans les réglages) : tout accès direct **sans badge** est **refusé (403)**, même en POST. À n'activer que si l'origine est injoignable hors Cloudflare (tunnel `cloudflared` / pare-feu IP Cloudflare), sinon risque de verrouillage.
- **Routes machine** (`/api/notify`, webhooks) : **toujours ouvertes** (HA / Proxmox jamais bloqués), protégées par le réseau.
- **Première install** : `ADMIN_PASSWORD` (et `CF_ACCESS_*` / `ALLOW_LOCAL_LOGIN`) dans `.env` sont **amorcés une fois** au démarrage — le mot de passe est **hashé** (PBKDF2). Ensuite, tout se gère dans les Paramètres.
- Ne publie **jamais** ton fichier `.env` (déjà ignoré par `.gitignore`).

> Le noyau de vérification du badge (`app/cloudflare_access.py`) et le thème d'interface sont **partagés à l'identique** avec les autres sites (socle `Site-base`), pour une sécurité et un look cohérents sur toute la flotte.

## Intégration Home Assistant (composant natif)

En plus du simple `rest_command` ci-dessus, BotPanel fournit un **vrai composant Home Assistant** (`custom_components/botpanel/`, compatible **HACS**) qui fait apparaître, dans HA :
- **un bouton par notification** (`button.botpanel_…`, appui = envoi Discord) — les nouvelles notifs apparaissent automatiquement ;
- une **action** `botpanel.envoyer` avec **liste déroulante de toutes les notifications** (slug/id en options avancées), utilisable dans les automatisations ;
- des **capteurs** : `binary_sensor` bot Discord en ligne, `sensor` envois du jour / envois total / notifications configurées / dernière alerte.

> **Sens unique** : Home Assistant **déclenche** (par identifiant), il ne configure jamais rien — tout le contenu reste défini sur BotPanel.

Le dépôt est **compatible HACS** (fichier `hacs.json` + composant dans `custom_components/botpanel/` à la racine).

**Étape 1 — récupérer la clé API** : dans BotPanel → **Paramètres → carte « API / Intégration »** → copier la **clé API** (générée automatiquement ; un « ? » explique tout à côté).

**Étape 2 — installer le composant dans Home Assistant** — deux méthodes :

- **Via HACS (recommandé, juste un lien)** : HACS → menu ⋮ → **Dépôts personnalisés** → coller l'URL du dépôt (`https://github.com/SuperNon0/botpanel`), catégorie **Intégration** → **Ajouter** → installer **BotPanel** → **redémarrer Home Assistant**.
- **Manuellement** : copier le dossier puis redémarrer HA :
  ```bash
  cp -r custom_components/botpanel /config/custom_components/
  ```

**Étape 3 — ajouter l'intégration** : Home Assistant → **Paramètres → Appareils et services → « + Ajouter une intégration »** → chercher **BotPanel** → saisir :
- **URL de BotPanel** : `http://IP_LXC:8080`
- **Clé API** : celle copiée à l'étape 1

**Étape 4 — vérifier** : un appareil **BotPanel** apparaît (un **bouton par notification** + les **capteurs**). Côté BotPanel, la carte « **l'intégration marche ?** » affiche « Module HA connecté ».

> HACS installe depuis la **branche par défaut** (`main`) : l'intégration doit donc être présente sur `main`. Le dépôt doit aussi être **public** avec une **description**.

Exemple d'automatisation complet et dépannage : [`custom_components/botpanel/GUIDE.md`](custom_components/botpanel/GUIDE.md).

**Utilisation dans une automatisation** — deux façons :
```yaml
# A) l'action dédiée : choix de la notif dans une liste déroulante
- action: botpanel.envoyer
  data:
    notification: button.botpanel_alerte_porte_garage

# B) appuyer directement sur le bouton de la notif
- action: button.press
  target:
    entity_id: button.botpanel_alerte_porte_garage
```

> Dans l'éditeur d'automatisation, l'action **BotPanel : Envoyer une notification** affiche un champ **Notification** avec la **liste déroulante** de toutes tes notifications (remplie automatiquement).

**Sécurité machine** : une **clé API** (`X-API-Key`, en-tête uniquement) protège les endpoints `/api/integration/*` ; elle se régénère dans les Paramètres (voyant « l'intégration marche ? » : HA joignable, dernière connexion du module, version). Les webhooks existants (`/api/notify`) restent ouverts **sans** clé (rétrocompatibilité HA/Proxmox).

## Intégration Proxmox VE / Proxmox Backup Server

Proxmox VE et PBS envoient leurs notifications (backups, sync, vérif…) **directement** à BotPanel via leur système natif de **webhook** — aucun script, tout se configure dans l'interface Proxmox (*Datacenter → Notifications*).

- **Endpoint** : `POST /api/integration/proxmox/<slug>` (protégé par la **clé API** `X-API-Key`). Le `<slug>` choisit la notification BotPanel à déclencher.
- **Corps du webhook** (format 3 lignes, robuste — pas de JSON à échapper) :
  ```
  {{ severity }}
  {{ title }}
  {{ message }}
  ```
- BotPanel **parse** le message et expose des variables à placer où tu veux dans la notif : `{var:statut}`, `{var:vmid}`, `{var:nom}`, `{var:duree}`, `{var:taille}`, `{var:datastore}`, `{var:message}`… La **couleur passe en rouge automatiquement** sur erreur.
- Dans l'éditeur de notification, le bouton **« 🖥️ Proxmox »** affiche la palette de variables **et** un **« ? »** avec la config exacte à coller (URL + en-tête + corps, boutons *Copier*). Le bouton **Tester** remplit des valeurs d'exemple.
- Côté Proxmox : ajouter une cible **Webhook** + un **Matcher** (ex. type `vzdump` pour les backups, `sync` pour l'envoi vers OVH). Historique BotPanel tagué **« Proxmox »**.

### Configurer Proxmox (interface native, aucun script)
1. **Datacenter → Notifications → Notification Targets → Add → Webhook** :
   - **URL** : `http://IP_LXC:8080/api/integration/proxmox/<slug>` (le slug de ta notif BotPanel)
   - **Header** : `X-API-Key: <ta clé BotPanel>`
   - **Body** : le format 3 lignes ci-dessus
2. **Add Matcher** pour router les événements voulus vers cette cible (ex. backups `vzdump`, sync `sync`).
3. Sur tes **jobs de backup**, mettre le **« Notification Mode » = notification system**.

> 💡 Le bouton **« 🖥️ Proxmox »** de l'éditeur affiche cette config **pré-remplie avec ton slug et ta clé** (boutons *Copier*).

## Évolutions futures

Voir [docs/V2-ROADMAP.md](docs/V2-ROADMAP.md).

> Note : les routes machine (`/api/notify`, webhooks) restent toujours accessibles sans login humain, pour ne pas casser les intégrations Home Assistant / Proxmox.

## Livrables

- Code source versionné
- Script de déploiement LXC (`deploy/install_lxc.sh`) + mise à jour (`deploy/update.sh`) + reset mot de passe (`deploy/reset_admin.sh`)
- Unit systemd (`deploy/botpanel.service`)
- Snippet HA prêt à coller (`deploy/homeassistant_rest_command.yaml`)
- **Composant Home Assistant** (`custom_components/botpanel/`, compatible HACS) + guide
- `.env.example` documenté

---

Dev : Noë FOUGERAY — botpanel.super-nono.cc
