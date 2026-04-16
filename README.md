# BotPanel

Bot Discord x Home Assistant, administré depuis un site web dédié.
Hébergé dans un conteneur LXC Proxmox.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![discord.py 2.x](https://img.shields.io/badge/discord.py-2.x-5865F2)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)

## Fonctionnalités

- **Notifications Discord** configurables depuis le site — HA n'a qu'un seul appel à faire (`rest_command.bot_discord` avec `id: <slug>`)
- **Boutons interactifs** (persistants, survivent au timeout 15min et aux redémarrages) : Supprimer, Snooze, boutons custom appelant un service HA
- **Commandes slash Discord** entièrement gérées depuis le site (service / script / scène / notification)
- **Monitoring temps réel** : messages épinglés édités à intervalle configurable (température & humidité, conso électrique)
- **Autocomplétion live** des entités et services HA dans tous les formulaires
- **Design FuelLog** (dark mode exclusif, DM Mono + DM Serif Display)

## Architecture

```
app/
├── main.py              # Lance bot + API dans la meme event loop
├── config.py            # Pydantic Settings (lit .env)
├── db/                  # SQLite async + repositories
├── bot/                 # discord.py : client, notifications, views, slash, monitoring
├── ha/                  # Client httpx pour l'API HA
├── api/                 # FastAPI : routes + web pages
└── web/                 # Templates Jinja + assets statiques
```

## Endpoints clés

| Route | Usage |
|-------|-------|
| `POST /api/notify` | Appelé par HA (`{"id": "<slug>"}`) |
| `GET /api/notifications` | CRUD notifications |
| `GET /api/commands` + `/quota` | CRUD commandes slash (limite 100) |
| `GET /api/monitoring` | CRUD blocs monitoring |
| `GET /api/ha/entities?domain=light` | Proxy HA pour autocomplétion |
| `GET /api/ha/services` | Proxy HA pour autocomplétion |
| `GET /notifications`, `/commands`, `/monitoring` | Pages du site |

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
| API / Web | FastAPI 0.115 + Uvicorn |
| DB | SQLite via aiosqlite |
| HTTP client | httpx |
| Config | pydantic-settings |
| Templates | Jinja2 |
| Conteneur | LXC Proxmox + systemd |

## Points d'attention

- **Boutons Discord** : les custom_id sont de la forme `bp:<action>:<notif_id>[:<btn_id>]`. Un dispatcher global (`on_interaction`) route les clics — aucun besoin de reconstruire les Views au boot.
- **Token HA** : créer un token avec uniquement les permissions nécessaires (lecture états + appel services).
- **Sync slash** : les commandes sont poussées sur la **guild** (pas en global) → propagation immédiate.
- **Monitoring** : chaque bloc garde l'ID du message épinglé en DB. Si le message a été supprimé côté Discord, il est recréé au cycle suivant.

## Livrables

- Code source versionné
- Script de déploiement LXC (`deploy/install_lxc.sh`)
- Unit systemd (`deploy/botpanel.service`)
- Snippet HA prêt à coller (`deploy/homeassistant_rest_command.yaml`)
- `.env.example` documenté

---

Dev : Noë FOUGERAY — botpanel.super-nono.cc
