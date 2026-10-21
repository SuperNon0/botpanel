# Serveur MCP BotPanel — piloter BotPanel depuis Claude

BotPanel expose un **serveur MCP** (Model Context Protocol) intégré. Une fois
connecté à Claude (claude.ai, app Claude ou Claude Desktop), **Claude peut agir
sur BotPanel** : lister / déclencher / créer des notifications, envoyer un message
ponctuel sur Discord, lire l'état et l'historique.

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
| `list_history` | Derniers envois (historique) |
| `check_update` | Vérifie si une mise à jour du code est disponible (git) — lecture seule |
| `update_site` | **Sauvegarde le code** puis met à jour + redémarre — **n'agit QUE si `confirm="OUI"`** |
| `rollback_site` | Revient à la dernière sauvegarde + redémarre — **n'agit QUE si `confirm="OUI"`** |

### Mise à jour pilotée par Claude (sécurisée)
Claude peut mettre à jour l'instance, mais avec une **double sécurité** :
1. L'outil `update_site` **refuse d'agir** sans `confirm="OUI"` (sinon il renvoie juste un aperçu des changements, sans rien modifier).
2. Avant d'appliquer, il crée un **tag de sauvegarde** `botpanel-pre-update` sur l'état actuel → rollback possible à tout moment avec `rollback_site`.

Dans la pratique : Claude **demande toujours** ton accord, puis, sur ton feu vert, fait la sauvegarde + `git fetch` + `git reset --hard origin/<branche>` + (pip si venv) + redémarrage. Prérequis identiques au bouton « Mettre à jour » (le dossier appartient à l'utilisateur du service, et une règle sudoers pour le restart si besoin).

## Sécurité
- Le serveur MCP est une **route machine** (`/mcp`) : **jamais** derrière le login
  humain Cloudflare, protégée **uniquement** par la clé API (comparaison constante).
- Si tu régénères la clé dans les Paramètres, remets-la à jour dans le connecteur.
- Transport : MCP « Streamable HTTP » (JSON-RPC), sans dépendance externe ajoutée.

## Détails techniques
- Endpoint : `POST /mcp` (JSON-RPC 2.0). `GET /mcp` → 405 (pas de flux SSE serveur).
- Implémentation : `app/api/routes/mcp_server.py` (aucune lib MCP tierce, pour ne
  pas diverger de la stack figée de BotPanel).
