# BotPanel

Bot Discord × Home Assistant, administré depuis un site web dédié.  
Hébergé dans un conteneur LXC Proxmox.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![discord.py 2.4](https://img.shields.io/badge/discord.py-2.4-5865F2)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)

## Fonctionnalités

- **Notifications Discord** configurables depuis le site — HA n'a qu'un seul appel à faire (`rest_command.bot_discord` avec `id: <slug>`)
- **Threads Discord** — les notifications d'un même groupe sont automatiquement regroupées dans un thread Discord dédié (créé, désarchivé ou recréé au besoin)
- **Boutons interactifs** (persistants, survivent au timeout 15 min et aux redémarrages) : Supprimer, Snooze, boutons custom appelant un service HA
- **Commandes slash Discord** : deux commandes fixes (`/ha`, `/clear`) + commandes personnalisées entièrement gérées depuis le site (service / script / scène / notification)
- **Monitoring temps réel** : messages épinglés édités à intervalle configurable (min. 30 s), recréés automatiquement si supprimés côté Discord
- **Templates dans les champs** : syntaxe BotPanel (`{state:sensor.x}`, `{attr:sensor.x:attr}`, `{unit:sensor.x}`) et Jinja HA natif (`{{ states('...') }}`, `{{ state_attr(...) }}`)
- **Autocomplétion live** des entités HA, services HA et channels Discord dans tous les formulaires
- **Page Paramètres** : presets de couleurs et de channels, gestion des threads actifs, mise à jour et redémarrage depuis l'UI
- **Page Historique** : logs de tous les envois et clics de boutons, avec filtre et purge
- **Design FuelLog** (dark mode exclusif, DM Mono + DM Serif Display)

## Le site web

Le site est l'interface d'administration du bot, accessible sur `http://IP_LXC:8080`. Il se compose de cinq sections.

### Notifications (`/notifications`)

Page principale. Elle liste toutes les notifications enregistrées, **groupées par `group_name`** si défini. Pour chaque notification on peut : tester l'envoi, éditer, cloner ou supprimer.

Le formulaire d'édition permet de configurer :
- **Identification** : slug (identifiant appelé depuis HA), channel Discord cible, nom de groupe (→ thread)
- **Embed** : titre, message (Markdown), couleur (sélecteur + presets), icône, footer, horodatage
- **Boutons** : cases "Supprimer" et "Snooze N min", plus des boutons custom déclenchant un service HA au clic
- **Champs** : fields Discord affichés en grille dans l'embed, avec templates d'états HA

Un **aperçu live** du rendu Discord est affiché pendant l'édition. Un bouton "Tester" envoie la notification dans Discord sans sauvegarder.

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

Quatre blocs :
- **Mise à jour** : affiche la branche et le commit git courants ; un bouton lance un `git pull` suivi d'un redémarrage automatique du service (la page se recharge toute seule quand le bot revient)
- **Couleurs préconfigurées** : palette de couleurs nommées disponibles dans le sélecteur rapide du formulaire notification
- **Channels Discord préconfigurés** : liste de channels avec leurs IDs, affichés dans la liste déroulante du formulaire ; un tableau des channels détectés par le bot permet de les ajouter en un clic
- **Threads Discord actifs** : liste tous les threads créés automatiquement par le bot ; bouton "Réinitialiser" par entrée pour forcer la recréation du thread au prochain envoi (utile si le thread a été supprimé sur Discord)

### Historique (`/historique`)

Journal de toutes les activités du bot : envois de notifications, clics sur les boutons (Supprimer, Snooze, action HA). Chaque entrée indique la notification concernée, l'utilisateur (pour les clics), le channel, l'horodatage et si l'opération a réussi. Filtrable et purgeable.

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
| `GET` | `/api/settings/threads` | Liste les threads Discord actifs |
| `DELETE` | `/api/settings/threads/{id}` | Réinitialise un thread (recréé au prochain envoi) |
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
| `/notifications` | Liste des notifications (groupées par groupe) |
| `/notifications/new` | Créer une notification |
| `/notifications/{id}` | Éditer une notification |
| `/commands` | Liste des commandes slash + quota |
| `/commands/new` | Créer une commande |
| `/commands/{id}` | Éditer une commande |
| `/monitoring` | Liste des blocs de monitoring |
| `/monitoring/new` | Créer un bloc |
| `/monitoring/{id}` | Éditer un bloc |
| `/settings` | Paramètres (presets, threads actifs, mise à jour, redémarrage) |
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
- **Threads Discord** : le thread_id est stocké en DB par `(group_name, channel_id)`. Si le thread est archivé, il est désarchivé avant l'envoi. S'il a été supprimé, il est recréé et le nouvel ID est sauvegardé. Les tests et previews depuis l'éditeur ignorent les threads et vont toujours dans le channel.
- **Token HA** : créer un token avec uniquement les permissions nécessaires (lecture états + appel services).
- **Sync slash** : les commandes sont poussées sur la **guild** (pas en global) → propagation immédiate. Les noms `ha` et `clear` sont réservés.
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
