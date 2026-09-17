# Connexion & sécurité du panel

BotPanel peut être protégé par un **mot de passe admin**. La protection est
**optionnelle** : tant qu'aucun mot de passe n'est défini, le panel reste ouvert
(pratique en réseau local ou derrière Cloudflare Access).

> 🔒 **Règle importante** : les routes machine (`/api/notify`, webhooks) ne sont
> **jamais** bloquées par l'authentification — Home Assistant et Proxmox continuent
> de fonctionner même quand la protection est activée.

---

## 1. Activer la protection

**Paramètres → Compte & sécurité → Activer la protection**

Choisis un nom d'utilisateur (par défaut `admin`) et un mot de passe (min. 6
caractères). À partir de là, les pages du site demandent une connexion ; une page
`/login` s'affiche pour les visiteurs non connectés.

Tu peux aussi définir le mot de passe dès l'**assistant de configuration** au
premier lancement (champ facultatif).

---

## 2. Changer le mot de passe

**Paramètres → Compte & sécurité → Changer le mot de passe**

Saisis le **mot de passe actuel** puis le **nouveau**. La session reste valide.

---

## 3. Mot de passe oublié (réinitialisation)

Sur le serveur (dans le conteneur / la machine où tourne BotPanel) :

```bash
cd /opt/botpanel
# Supprimer le mot de passe (le panel redevient ouvert) :
bash deploy/reset_admin.sh
# ...ou définir directement un nouveau mot de passe :
bash deploy/reset_admin.sh "mon-nouveau-mot-de-passe"

sudo systemctl restart botpanel
```

Ensuite, reconnecte-toi (ou redéfinis un mot de passe dans **Paramètres**).

---

## 4. Cloudflare Access (option recommandée)

Si tu exposes le panel sur Internet, le plus simple et le plus sûr est de le placer
derrière **Cloudflare Zero Trust (Access)** avec authentification Google :

- Cloudflare gère l'identité **avant** que le trafic n'atteigne le panel.
- Tu autorises une liste d'e-mails dans la *policy* Cloudflare.
- Dans ce cas, tu peux **laisser la protection par mot de passe désactivée**
  (Cloudflare fait déjà le travail).

⚠️ Cloudflare ne protège que le trafic qui **passe par Cloudflare**. Bloque l'accès
direct au port `8080` (firewall) pour que tout passe par le tunnel — **sauf** l'accès
local de Home Assistant à `/api/notify`, qu'il faut garder joignable.

---

## 5. Pièges à éviter

- ⚠️ **Ne bloque pas `/api/notify`** : Home Assistant en a besoin pour déclencher les notifications.
- 🔑 **Mot de passe fort** si le panel est accessible depuis Internet sans Cloudflare.
- 🗑️ Changer/supprimer le mot de passe **invalide les sessions** en cours (reconnexion nécessaire).
- 🧩 Le mot de passe est stocké **haché** (PBKDF2), jamais en clair.
- 💾 Le mot de passe est dans la base (`data/botpanel.db`) — il est donc inclus dans
  l'export/import ; ne partage pas ta sauvegarde n'importe où.
- 🔁 Après un `reset_admin.sh`, **redémarre** le service pour appliquer le changement.

---

## Connexion via Cloudflare Access (le « badge »)

BotPanel accepte **deux portes d'entrée** quand la protection par mot de passe est activée :

1. **En local (LAN)** → **mot de passe** admin (voir plus haut).
2. **Via Cloudflare Access** → **connexion automatique, sans mot de passe** : Cloudflare a
   déjà vérifié ton e-mail Google, et BotPanel vérifie le **badge signé** (`Cf-Access-Jwt-Assertion`).

> 🔐 **Anti-usurpation** : BotPanel vérifie la **signature du badge** (JWT RS256 + `aud` + `iss`)
> contre les clés publiques de ton équipe Cloudflare. Un simple en-tête `Cf-Access-Authenticated-User-Email`
> **forgé en local** (sans badge signé valide) est **ignoré** → personne ne peut se faire passer
> pour une connexion Cloudflare.

### Configuration

**Paramètres → Badge Cloudflare / Accès** (ou via `.env`) :

| Champ | Exemple | Rôle |
|---|---|---|
| **Équipe** | `super-nono` | nom d'équipe **seul** (pas l'URL) |
| **AUD** | `a1b2c3…` | Application Audience tag de l'app Access |
| **Vérifier le badge** | coché | vérifie la signature (recommandé) |

Le bouton **Tester** affiche un diagnostic (badge reçu ? équipe/AUD ? vérification OK ? e-mail du badge).
La config saisie dans les Paramètres **prime** sur le `.env`.

### Important

- Les **routes machine** (`/api/notify`, webhooks) restent **toujours ouvertes** — HA/Proxmox
  ne présentent pas de badge et ne doivent pas être bloqués.
- Rends l'origine **injoignable sans Cloudflare** (tunnel `cloudflared` / pare-feu IP Cloudflare)
  pour l'interface web, tout en laissant `/api/notify` joignable sur le LAN.
- Garde un **mot de passe local** en secours : si Cloudflare tombe, tu peux toujours entrer sur le LAN.
