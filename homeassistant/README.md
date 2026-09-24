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
Copie le dossier `custom_components/botpanel/` dans la configuration de Home
Assistant, pour obtenir :

```
<config Home Assistant>/custom_components/botpanel/
```

Exemple (add-on « Samba » ou SSH) :
```bash
cp -r homeassistant/custom_components/botpanel /config/custom_components/
```
Puis **redémarre Home Assistant** (Paramètres → Système → Redémarrer).

## 3. Ajouter l'intégration
Home Assistant → **Paramètres → Appareils et services → Ajouter une intégration**
→ cherche **BotPanel** → saisis :
- **URL de BotPanel** : ex. `http://192.168.1.50:8080`
- **Clé API** : celle copiée à l'étape 1

## Ce que tu obtiens
Un appareil **BotPanel** regroupant :
- `button.botpanel_<nom>` : **un bouton par notification** (appui = envoi Discord)
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
      # Option A — appuyer sur le bouton de la notif (autocomplété par HA)
      - action: button.press
        target:
          entity_id: button.botpanel_alerte_porte_garage
      # Option B — l'action dédiée (par slug)
      # - action: botpanel.envoyer
      #   data:
      #     slug: notif_porte_garage
```

## Notes
- Les boutons des **nouvelles** notifications apparaissent automatiquement (au
  prochain rafraîchissement, ~30 s). En cas de **suppression ou de renommage de
  slug** dans BotPanel, **recharge l'intégration** (menu ⋮ → Recharger) pour
  retirer les anciens boutons.
- Rien n'est envoyé depuis HA vers la configuration de BotPanel : HA ne fait que
  lire l'état et déclencher des notifications existantes.
- Sécurité : toutes les requêtes utilisent l'en-tête `X-API-Key`. Si tu régénères
  la clé dans BotPanel, remets-la à jour ici (supprime puis rajoute l'intégration).
