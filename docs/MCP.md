# Serveur MCP BotPanel — piloter BotPanel depuis Claude

BotPanel expose un **serveur MCP** (Model Context Protocol) intégré. Une fois
connecté à Claude (claude.ai, app Claude ou Claude Desktop), **Claude peut agir
sur BotPanel** : gérer les notifications, les commandes slash, les blocs de
monitoring et les couleurs préconfigurées, envoyer un message ponctuel sur Discord, lire l'état, l'historique et
les erreurs.

> Exemple : « Claude, crée une notif qui prévient quand la porte du garage
> s'ouvre » → Claude lit l'entité dans Home Assistant **et** crée la notification
> dans BotPanel, en direct.

## L'URL et la clé
- **URL du serveur** : `https://TON-DOMAINE/mcp` (ex. `https://botpanel.super-nono.cc/mcp`)
- **Clé** : la **clé API BotPanel** (Paramètres → carte « API / Intégration »).
  C'est la même clé que pour Home Assistant / Proxmox.

Deux façons de présenter la clé :
1. **En-tête** `Authorization: Bearer <clé>` (recommandé) ou `X-API-Key: <clé>`
2. **Dans l'URL** : `https://TON-DOMAINE/mcp/<clé>` (pratique si le client ne gère
   pas les en-têtes personnalisés — attention, la clé apparaît alors dans les logs)

## ⚠️ Cloudflare Access — ouvrir le chemin `/mcp`

Le site est protégé par **Cloudflare Access** (login humain). Proxmox et Home
Assistant contournent ça car ils joignent BotPanel par l'**IP LAN**
(`http://IP_LXC:8080`). Mais **Claude est sur Internet** : il passe par le domaine
public → **Cloudflare bloque** la connexion avant même BotPanel.

Il faut donc dire à Cloudflare de **laisser passer `/mcp` sans login** (BotPanel
le protège déjà avec la clé API). Dans **Cloudflare Zero Trust** :

1. **Access → Applications → Add an application → Self-hosted**
2. **Application domain** : `botpanel.super-nono.cc`, **Path** : `mcp` (ajoute une
   2ᵉ entrée `mcp/*` pour couvrir l'URL-avec-clé)
3. **Policies → Add a policy** : Action = **Bypass**, Include = **Everyone**
4. **Save**. Place cette application **au-dessus** de celle qui protège tout le
   domaine (l'ordre compte : la plus précise d'abord).

Résultat : `/mcp` devient joignable par Claude **sans** login Cloudflare ; le reste
du site reste protégé ; et `/mcp` reste verrouillé par la **clé API** BotPanel.

> Alternative plus stricte : au lieu de **Bypass**, utilise un **Service Token**
> Cloudflare (politique « Service Auth ») et fais envoyer par le client les en-têtes
> `CF-Access-Client-Id` / `CF-Access-Client-Secret`. Plus sûr, mais le client MCP
> doit pouvoir envoyer ces deux en-têtes (OK avec `mcp-remote --header`).

> 🔒 Avec un **Bypass**, préfère l'auth **par en-tête** (pas la clé dans l'URL) :
> sinon la clé apparaît dans les logs Cloudflare.

## Connexion

### claude.ai / app Claude (connecteur personnalisé)
Réglages → **Connecteurs** → **Ajouter un connecteur personnalisé** → coller l'URL.
- Si on te demande une authentification par en-tête : mets `Authorization` =
  `Bearer <clé>`.
- Sinon, utilise directement l'URL **avec la clé dedans** :
  `https://TON-DOMAINE/mcp/<clé>`.

### Claude Desktop (via le pont `mcp-remote`)
Dans `claude_desktop_config.json` :
```json
{
  "mcpServers": {
    "botpanel": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://TON-DOMAINE/mcp",
        "--header",
        "Authorization: Bearer TA_CLE_API"
      ]
    }
  }
}
```
Puis redémarre Claude Desktop.

## Outils exposés
| Outil | Rôle |
|-------|------|
| `list_notifications` | Liste les notifications (slug, titre, groupe) |
| `send_notification` | Déclenche une notif existante (par slug, + variables) |
| `create_notification` | Crée une nouvelle notification (titre, message, salon, couleur, champs, **images**, **boutons d'action HA**, boutons Supprimer/Snooze) |
| `update_notification` | Modifie une notification existante (par slug) — seuls les champs fournis changent ; peut la renommer |
| `delete_notification` | Supprime définitivement une notification (par slug) |
| `send_quick_message` | Envoie un message ponctuel sur un salon Discord (sans sauvegarder) |
| `get_state` | État : bot en ligne, envois du jour / total, dernière alerte |
| `list_history` | Historique (envois, commandes, monitoring, clics), filtrable par type |
| `list_errors` | Erreurs récentes : échecs de l'historique + avertissements/erreurs du serveur depuis le dernier redémarrage |
| `list_commands` | Liste les commandes slash (nom, action, état) |
| `get_command` | Détail complet d'une commande (par nom) |
| `create_command` | Crée une commande slash (action HA, script, scène, notification ou simple réponse ; réponse en encadré, boutons HA) — synchronisée sur Discord |
| `update_command` | Modifie une commande (par nom) — seuls les champs fournis changent ; peut la renommer |
| `delete_command` | Supprime définitivement une commande |
| `run_command` | Exécute une commande comme sur Discord et renvoie sa réponse (tracé dans l'historique, source `mcp`) |
| `list_monitoring` | Liste les blocs de monitoring (id, nom, actif, salon, fréquence) |
| `get_monitoring` | Détail d'un bloc (par id) + rendu actuel avec les vraies valeurs HA |
| `create_monitoring` | Crée un bloc (champs HA, description, images, boutons HA, bouton Actualiser) — inactif sauf `enabled=true` |
| `update_monitoring` | Modifie un bloc (par id) — seuls les champs fournis changent ; `enabled=true` l'active |
| `delete_monitoring` | Supprime définitivement un bloc |
| `send_monitoring` | Envoie / met à jour tout de suite le message Discord d'un bloc actif |
| `list_colors` | Liste les couleurs préconfigurées (nom + hex) |
| `set_color` | Crée une couleur préconfigurée, ou la modifie si le nom existe (peut la renommer) |
| `delete_color` | Supprime une couleur préconfigurée |
| `get_notification` | Détail complet d'une notification (par slug) |
| `duplicate_notification` | Duplique une notification (slug `new_slug`, sinon `<slug>_copy`) |
| `preview_notification` | Aperçu d'une notification avec les vraies valeurs HA, **sans l'envoyer** |
| `duplicate_command` | Duplique une commande (copie `<nom>-copie`, créée désactivée) |
| `duplicate_monitoring` | Duplique un bloc (copie créée inactive) |
| `list_channels` | Liste les salons Discord (texte, ou `kind=forum`) avec leur id |
| `list_forum_posts` | Liste les posts actifs d'un salon forum |
| `list_favorite_channels` / `set_favorite_channel` / `delete_favorite_channel` | Gère les salons favoris |
| `list_threads` / `delete_thread` | Liste les fils Discord des groupes / en oublie un (le prochain envoi recrée un fil) |
| `get_stats` | Statistiques du tableau de bord (jour, semaine, 7 derniers jours) |
| `purge_history` | Supprime l'historique de plus de N jours — **n'agit QUE si `confirm="OUI"`** |
| `get_system_info` | Version (commit), branche et dossier du site |
| `restart_site` | Redémarre le service — **n'agit QUE si `confirm="OUI"`** |
| `get_home_url` / `set_home_url` | Lit / change l'URL d'accueil des Paramètres |
| `check_update` | Vérifie si une mise à jour du code est disponible (git) — lecture seule |
| `update_site` | **Sauvegarde le code** puis met à jour + redémarre — **n'agit QUE si `confirm="OUI"`** |
| `rollback_site` | Revient à la dernière sauvegarde + redémarre — **n'agit QUE si `confirm="OUI"`** |

### Mise à jour pilotée par Claude (sécurisée)
Claude peut mettre à jour l'instance, mais avec une **double sécurité** :
1. L'outil `update_site` **refuse d'agir** sans `confirm="OUI"` (sinon il renvoie juste un aperçu des changements, sans rien modifier).
2. Avant d'appliquer, il crée un **tag de sauvegarde** `botpanel-pre-update` sur l'état actuel → rollback possible à tout moment avec `rollback_site`.

Dans la pratique : Claude **demande toujours** ton accord, puis, sur ton feu vert, fait la sauvegarde + `git fetch` + `git reset --hard origin/<branche>` + (pip si venv) + redémarrage. Prérequis identiques au bouton « Mettre à jour » (le dossier appartient à l'utilisateur du service, et une règle sudoers pour le restart si besoin).

> Après une mise à jour qui ajoute des outils : **reconnecte le connecteur** puis
> ouvre une **nouvelle conversation** (une conversation déjà ouverte garde l'ancienne
> liste d'outils).

> Les erreurs serveur lues par `list_errors` sont gardées **en mémoire** (200
> dernières, niveau WARNING et plus) : elles repartent de zéro à chaque redémarrage.

> Volontairement **non exposés** au MCP : mot de passe, réglages Cloudflare,
> régénération de la clé API (Claude se couperait l'accès) et import de sauvegarde.

## Sécurité
- Le serveur MCP est une **route machine** (`/mcp`) : **jamais** derrière le login
  humain Cloudflare, protégée **uniquement** par la clé API (comparaison constante).
- Si tu régénères la clé dans les Paramètres, remets-la à jour dans le connecteur.
- Transport : MCP « Streamable HTTP » (JSON-RPC), sans dépendance externe ajoutée.

## Détails techniques
- Endpoint : `POST /mcp` (JSON-RPC 2.0). `GET /mcp` → 405 (pas de flux SSE serveur).
- Implémentation : `app/api/routes/mcp_server.py` (aucune lib MCP tierce, pour ne
  pas diverger de la stack figée de BotPanel).
