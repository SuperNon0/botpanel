# BotPanel

Bot Discord × Home Assistant, administré depuis un site web dédié.  
Hébergé dans un conteneur LXC Proxmox.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![discord.py 2.4](https://img.shields.io/badge/discord.py-2.4-5865F2)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)

## Fonctionnalités

- **Notifications Discord** configurables depuis le site — HA n'a qu'un seul appel à faire (`rest_command.bot_discord` avec `id: <slug>`)
- **Boutons interactifs** (persistants, survivent au timeout 15 min et aux redémarrages) : Supprimer, Snooze, boutons custom appelant un service HA
- **Commandes slash Discord** entièrement gérées depuis le site (service / script / scène / notification)
- **Monitoring temps réel** : messages épinglés édités à intervalle configurable (min. 30 s), recréés automatiquement si supprimés côté Discord
- **Templates dans les champs** : syntaxe BotPanel (`{state:sensor.x}`, `{attr:sensor.x:attr}`, `{unit:sensor.x}`) et Jinja HA natif (`{{ states('...') }}`, `{{ state_attr(...) }}`)
- **Autocomplétion live** des entités HA, services HA et channels Discord dans tous les formulaires
- **Page Paramètres** : presets de couleurs et de channels Discord réutilisables dans tous les formulaires
- **Page Historique** : logs de tous les envois et clics de boutons, avec filtre et purge
- **Mise à jour depuis l'UI** : git pull + redémarrage du service en un clic depuis la page Paramètres
- **Design FuelLog** (dark mode exclusif, DM Mono + DM Serif Display)

## Architecture

```
app/
├── main.py              # Lance bot + API dans la même event loop asyncio
├── config.py            # Pydantic Settings (lit .env)
├── db/
│   ├── database.py      # SQLite async (aiosqlite)
│   ├── models.py        # Schémas Pydantic
│   └── repositories/    # Accès données par entité (notifications, commands, monitoring, logs, settings)
├── bot/                 # discord.py : client, notifications, views, slash, monitoring
├── ha/                  # Client httpx pour l'API HA
├── api/
│   ├── server.py        # Instanciation FastAPI + montage des routeurs
│   └── routes/          # Un fichier par groupe de routes
└── web/
    ├── templates/        # Templates Jinja2
    └── static/           # CSS + JS
```

## Endpoints

### API REST

| Méthode | Route | Usage |
|---------|-------|-------|
| `POST` | `/api/notify` | Appelé par HA — `{"id": "<slug>"}` |
| `GET` | `/api/notifications` | Liste toutes les notifications |
| `POST` | `/api/notifications` | Crée une notification |
| `GET` | `/api/notifications/{id}` | Détail d'une notification |
| `PUT` | `/api/notifications/{id}` | Modifie une notification |
| `DELETE` | `/api/notifications/{id}` | Supprime une notification |
| `POST` | `/api/notifications/{id}/test` | Envoie la notification en test |
| `POST` | `/api/notifications/{id}/duplicate` | Duplique (slug `<original>_copy`) |
| `POST` | `/api/notifications/preview` | Prévisualise sans sauvegarder |
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
| `GET` | `/api/settings/colors` | Presets de couleurs sauvegardés |
| `PUT` | `/api/settings/colors` | Enregistre les presets de couleurs |
| `GET` | `/api/settings/channels` | Presets de channels sauvegardés |
| `PUT` | `/api/settings/channels` | Enregistre les presets de channels |
| `GET` | `/api/logs` | Historique des envois et clics (filtres : `limit`, `kind`, `notification_id`) |
| `DELETE` | `/api/logs/older/{days}` | Purge les logs de plus de N jours |
| `GET` | `/api/system/info` | Infos système (commit et branche git courants) |
| `POST` | `/api/system/update` | `git fetch && git pull --ff-only` |
| `POST` | `/api/system/restart` | `systemctl restart botpanel` (détaché) |
| `GET` | `/health` | Vérification de santé — `{"status": "ok"}` |
| `GET` | `/api/docs` | Documentation Swagger UI |

### Pages web

| Route | Page |
|-------|------|
| `/notifications` | Liste des notifications |
| `/notifications/new` | Créer une notification |
| `/notifications/{id}` | Éditer une notification |
| `/commands` | Liste des commandes slash |
| `/commands/new` | Créer une commande |
| `/commands/{id}` | Éditer une commande |
| `/monitoring` | Liste des blocs de monitoring |
| `/monitoring/new` | Créer un bloc |
| `/monitoring/{id}` | Éditer un bloc |
| `/settings` | Paramètres (presets couleurs & channels, mise à jour, redémarrage) |
| `/historique` | Historique des envois et clics de boutons |

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
| Conteneur | LXC Proxmox + systemd |

## Points d'attention

- **Boutons Discord** : les `custom_id` sont de la forme `bp:<action>:<notif_id>[:<btn_id>]` (actions : `del`, `snz`, `btn`, `preview`). Un dispatcher global (`on_interaction`) route les clics — aucun besoin de reconstruire les Views au boot.
- **Token HA** : créer un token avec uniquement les permissions nécessaires (lecture états + appel services).
- **Sync slash** : les commandes sont poussées sur la **guild** (pas en global) → propagation immédiate.
- **Monitoring** : chaque bloc garde l'ID du message épinglé en DB. Si le message a été supprimé côté Discord, il est recréé au cycle suivant. Intervalle minimum : 30 secondes.
- **Redémarrage depuis l'UI** : `POST /api/system/restart` lance le restart en tâche détachée. L'API devient inaccessible quelques secondes ; le frontend poll `/health` pour détecter le retour.
- **Mise à jour depuis l'UI** : `POST /api/system/update` effectue un `git pull --ff-only`. Le sudoers est configuré automatiquement par `install_lxc.sh` — aucune manipulation manuelle nécessaire.

## Livrables

- Code source versionné
- Script de déploiement LXC (`deploy/install_lxc.sh`)
- Unit systemd (`deploy/botpanel.service`)
- Snippet HA prêt à coller (`deploy/homeassistant_rest_command.yaml`)
- `.env.example` documenté

---

Dev : Noë FOUGERAY — botpanel.super-nono.cc
