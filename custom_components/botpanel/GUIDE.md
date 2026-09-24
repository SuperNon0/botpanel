# Intégration BotPanel pour Home Assistant

Ce dossier contient le **composant Home Assistant** qui connecte HA à BotPanel :
des **boutons** (un par notification), une **action** `botpanel.envoyer`, et des
**capteurs** (bot en ligne, envois, dernière alerte).

> Principe : Home Assistant **déclenche** les notifications (par identifiant).
> Il ne configure jamais rien — tout le contenu reste défini dans BotPanel.

## 1. Récupérer la clé API (dans BotPanel)
BotPanel → **Paramètres → API / Intégration** → copie la **clé API**
(elle est générée automatiquement au premier affichage).

## 2. Installer le composant dans Home Assistant

### Via HACS (recommandé — juste un lien)
HACS → menu ⋮ → **Dépôts personnalisés** → coller l'URL du dépôt
(`https://github.com/SuperNon0/botpanel`), catégorie **Intégration** →
**Ajouter** → installer **BotPanel** → **redémarrer Home Assistant**.

> HACS installe depuis la branche par défaut (`main`) : l'intégration doit y être
> présente, et le dépôt doit être **public** avec une **description**.

### Ou manuellement (SSH / add-on Samba)
```bash
cp -r custom_components/botpanel /config/custom_components/
```
Puis **redémarre Home Assistant** (Paramètres → Système → Redémarrer).

## 3. Ajouter l'intégration
Home Assistant → **Paramètres → Appareils et services → Ajouter une intégration**
→ cherche **BotPanel** → saisis :
- **URL de BotPanel** : ex. `http://192.168.1.50:8080`
- **Clé API** : celle copiée à l'étape 1

## Ce que tu obtiens
Un appareil **BotPanel** regroupant :
- `button.botpanel_<nom>` : **un bouton par notification** (appui = envoi Discord).
  Le nom affiché (et dans la liste déroulante de l'action) montre le **titre + le
  slug entre parenthèses**, ex. `Serrure d'entrée fermée (serrure_entree)`, pour
  retrouver facilement une notif quand on la déclenchait par slug.
- `binary_sensor.botpanel_bot_en_ligne`
- `sensor.botpanel_envois_du_jour`, `…_envois_total`, `…_notifications_configurees`
- `sensor.botpanel_derniere_alerte` (horodatage + slug/source en attributs)

## Exemple d'automatisation
Déclencher une notif quand une porte s'ouvre :
```yaml
automation:
  - alias: "Alerte porte garage"
    trigger:
      - platform: state
        entity_id: binary_sensor.porte_garage
        to: "on"
    action:
      # Option A — l'action dédiée : liste déroulante de toutes les notifications
      - action: botpanel.envoyer
        data:
          notification: button.botpanel_alerte_porte_garage
      # Option B — appuyer directement sur le bouton de la notif
      # - action: button.press
      #   target:
      #     entity_id: button.botpanel_alerte_porte_garage
```

> Dans l'éditeur d'automatisation, l'action **BotPanel : Envoyer une notification**
> affiche un champ **Notification** avec une **liste déroulante** de toutes tes
> notifications (elle se remplit toute seule). Les champs *slug* et *id* restent
> disponibles en options avancées.

## Logo de l'intégration
Home Assistant récupère le logo depuis le dépôt officiel
[home-assistant/brands](https://github.com/home-assistant/brands), pas depuis ce
dossier. Les images prêtes à soumettre (aux bonnes tailles) et la démarche sont
dans [`brands/`](../../brands/) à la racine du dépôt.

## Notes
- Les boutons des **nouvelles** notifications apparaissent automatiquement (au
  prochain rafraîchissement, ~30 s). En cas de **suppression ou de renommage de
  slug** dans BotPanel, **recharge l'intégration** (menu ⋮ → Recharger) pour
  retirer les anciens boutons.
- Rien n'est envoyé depuis HA vers la configuration de BotPanel : HA ne fait que
  lire l'état et déclencher des notifications existantes.
- Sécurité : toutes les requêtes utilisent l'en-tête `X-API-Key`. Si tu régénères
  la clé dans BotPanel, remets-la à jour ici (supprime puis rajoute l'intégration).
