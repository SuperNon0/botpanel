# API — envoyer une notification depuis un autre projet

BotPanel expose une API très simple pour que **n'importe quel projet** puisse
déclencher une notification Discord. Le principe :

1. Tu crées la notification **une fois** dans BotPanel (titre, message, couleur,
   channel, boutons…) et tu lui donnes un **slug** (identifiant).
2. Ton projet envoie une simple requête HTTP avec ce slug.
3. BotPanel s'occupe de tout le reste (mise en forme, envoi Discord).

> ✅ Ton projet n'a **rien à savoir** de Discord : il envoie juste un slug. Toute la
> notification est gérée côté BotPanel — tu peux la modifier quand tu veux sans
> retoucher le projet.

---

## Endpoint

```
POST  {BOTPANEL_URL}/api/notify
Content-Type: application/json

{ "id": "<slug_de_la_notification>" }
```

- `{BOTPANEL_URL}` = l'adresse de ton BotPanel, ex. `http://192.168.1.20:8080`
  (ou ton domaine si exposé, ex. `https://botpanel.exemple.com`).
- `id` = le **slug** de la notification créée dans le panel.

### Authentification

Cette route est **toujours ouverte** : même si tu as activé la protection par mot
de passe sur le panel, `/api/notify` reste accessible (sinon Home Assistant et tes
projets seraient bloqués). Aucun token n'est requis.

> 🔒 Garde donc BotPanel sur ton **réseau local** ou derrière un tunnel/VPN si tu ne
> veux pas que cette route soit joignable depuis Internet.

### Réponses

| Code | Signification |
|------|---------------|
| `200` | Notification envoyée. Corps : `{"status": "sent", "message_id": "..."}` |
| `404` | Slug inconnu ou échec d'envoi (channel introuvable, etc.) |
| `422` | Corps JSON invalide (champ `id` manquant) |

---

## Exemples

### cURL
```bash
curl -X POST http://192.168.1.20:8080/api/notify \
  -H "Content-Type: application/json" \
  -d '{"id": "backup_termine"}'
```

### Python
```python
import requests

BOTPANEL_URL = "http://192.168.1.20:8080"

def notify(slug: str) -> None:
    requests.post(f"{BOTPANEL_URL}/api/notify", json={"id": slug}, timeout=5)

notify("backup_termine")
```

### Node.js (fetch)
```js
const BOTPANEL_URL = "http://192.168.1.20:8080";

async function notify(slug) {
  await fetch(`${BOTPANEL_URL}/api/notify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: slug }),
  });
}

await notify("backup_termine");
```

### PHP
```php
$url = "http://192.168.1.20:8080/api/notify";
$ch = curl_init($url);
curl_setopt_array($ch, [
  CURLOPT_POST => true,
  CURLOPT_HTTPHEADER => ["Content-Type: application/json"],
  CURLOPT_POSTFIELDS => json_encode(["id" => "backup_termine"]),
  CURLOPT_RETURNTRANSFER => true,
]);
curl_exec($ch);
curl_close($ch);
```

### Bash (fonction réutilisable)
```bash
BOTPANEL_URL="http://192.168.1.20:8080"
notify() { curl -s -X POST "$BOTPANEL_URL/api/notify" \
  -H "Content-Type: application/json" -d "{\"id\": \"$1\"}" > /dev/null; }

notify "backup_termine"
```

### Home Assistant (`rest_command`)
```yaml
rest_command:
  bot_discord:
    url: "http://192.168.1.20:8080/api/notify"
    method: POST
    content_type: "application/json"
    payload: '{"id": "{{ id }}"}'
```
Puis dans une automatisation :
```yaml
action:
  - service: rest_command.bot_discord
    data:
      id: "backup_termine"
```

---

## Bonnes pratiques d'intégration

Pour tes futurs projets, mets ces deux valeurs dans la **configuration** (fichier
`.env`, variables d'environnement, settings…) plutôt qu'en dur dans le code :

```env
BOTPANEL_URL=http://192.168.1.20:8080
```

Et garde une petite fonction `notify(slug)` (voir exemples ci-dessus) que tu appelles
partout où le projet doit prévenir. Ainsi, changer l'adresse de BotPanel ne demande
qu'une seule modification.

## Dépannage

- **`404`** : vérifie que le slug existe bien dans BotPanel (page Notifications) et
  qu'il est écrit exactement pareil (minuscules, underscores).
- **Connexion refusée / timeout** : le projet n'atteint pas BotPanel — vérifie
  l'adresse, le port, et que les deux sont sur le même réseau (ou le tunnel).
- **Rien n'arrive sur Discord alors que la réponse est `200`** : le bot n'est
  peut-être pas connecté, ou le channel de la notification n'existe plus — regarde
  la page **Historique** du panel.
