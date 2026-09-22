# Feuille de route — V2 BotPanel · Intégration Home Assistant

> Spécification validée avec l'utilisateur (discussion de cadrage). Sert de
> référence pour le développement. Une fonctionnalité implémentée est retirée
> d'ici et documentée dans le `README.md`.

## Décisions validées

**Approche**
- Intégration **custom** (composant Python Home Assistant, compatible HACS),
  hébergée **dans le même dépôt** sous `homeassistant/custom_components/botpanel/`.

**Ce qui apparaît dans Home Assistant**
- **Boutons** : un `button.botpanel_<slug>` par notification (appui = envoi).
- **Action** `botpanel.envoyer` avec la liste des notifs (autocomplétion).
- **Capteurs** (lecture seule) : bot Discord en ligne, envois du jour, envois
  total, dernière alerte, nombre de notifications configurées.

**Règles**
- Déclenchement **par ID seul** : HA déclenche, il ne configure jamais rien.
  Tout le contenu est défini/résolu par BotPanel (les `{state:...}`, `{var:...}`,
  Jinja HA restent résolus par BotPanel à l'envoi).
- **Sens BotPanel → HA** limité à des capteurs en lecture seule.

**Sécurité**
- **Clé API** (`X-API-Key`) générée dans BotPanel (Paramètres → carte « API /
  Intégrations »).
- `/api/notify` **reste ouvert sans clé** (rétrocompatibilité HA/Proxmox actuels) ;
  la clé est exigée **uniquement** sur les nouveaux endpoints d'intégration.

## Fonctionnalités additionnelles validées
- ✅ **FAIT — Aperçu live avec vraies valeurs HA** dans l'éditeur : l'aperçu
  résout les placeholders HA (`{state:}`, `{attr::}`, `{unit:}`, Jinja) avec les
  valeurs réelles (endpoint `POST /api/notifications/resolve-preview`), sans
  envoyer sur Discord ; les `{var:...}` restent visibles. Documenté dans le README.
- ✅ **DÉJÀ PRÉSENT — Sélecteur d'entités HA** dans l'éditeur : bouton « + entité »
  qui insère `{state:...|--}` (existait déjà, s'associe à l'aperçu live).
- **Source dans l'historique** : chaque envoi indique son origine (manuel /
  bouton / automatisation Home Assistant).
- **Carte « l'intégration marche ? »** : encart de diagnostic (voyant + test)
  confirmant que HA et BotPanel communiquent.

## Mis de côté (pas maintenant)
- Passer des variables au déclenchement depuis HA (on reste « par ID pur »).
- Exemples de notifications prêts à cloner (peut-être plus tard).

## Ordre de développement (phases livrables une par une)
1. ✅ **FAIT — Aperçu live HA** : endpoint `POST /api/notifications/resolve-preview`
   + éditeur qui affiche les valeurs réelles. Sélecteur d'entités HA : déjà présent.
2. **Clé API** : génération + carte Paramètres « API / Intégrations » +
   middleware `X-API-Key`. **+ Carte diagnostic** « l'intégration marche ? ».
3. **API intégration** : `GET /api/integration/ping`, `/notifications`, `/state`.
4. **Composant Home Assistant** : config flow (URL + clé), coordinator (~30 s),
   boutons, capteurs, service `botpanel.envoyer`, regroupés sous un appareil
   « BotPanel ».
5. **Source dans l'historique** : marquer l'origine des envois (manuel / HA).
6. **Doc & tests** : guide d'installation HACS, exemple d'automatisation, tests
   des endpoints (clé, listes, state) et validation de la structure du composant.

## Repères techniques (existant réutilisable)
- Placeholders HA déjà supportés (résolus à l'envoi via `ha_client.get_state`) :
  `{state:sensor.x}`, `{attr:sensor.x:friendly_name}`, `{unit:sensor.x}`, et le
  Jinja HA `{{ states('sensor.x') }}` — voir `app/bot/notifications.py`
  (`_resolve_template`).
- Autocomplétion d'entités HA déjà en place (`attachAutocomplete`, `app/api/ha`).
- Déclenchement par ID existant : `POST /api/notify {id}` (à conserver ouvert).

## Idées plus larges (à rediscuter, hors V2)
- SSO Cloudflare centralisé pour toute la flotte (le noyau `cloudflare_access.py`
  est déjà partagé, ce qui prépare le terrain).
