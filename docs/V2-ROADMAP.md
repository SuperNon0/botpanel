# Feuille de route BotPanel — à faire / idées

> Les fonctionnalités **implémentées** sont retirées d'ici et documentées dans le
> `README.md`. Ce fichier ne garde que ce qui reste à faire ou à décider.

## À faire (manuel, hors code)
- **Logo de l'intégration HA** : soumettre `brands/custom_integrations/botpanel/`
  (icon.png + @2x, déjà prêts) au dépôt officiel
  [home-assistant/brands](https://github.com/home-assistant/brands) via une PR.
  Tant que ce n'est pas mergé là-bas, HA/HACS affichent l'icône par défaut. Voir
  `brands/README.md` pour la démarche.

## À affiner
- **Parseur Proxmox** (`app/api/routes/integration.py`, `parse_proxmox`) : caler
  l'extraction fine des champs (durée, taille, nom de VM) sur un **vrai message
  de backup** Proxmox/PBS. Aujourd'hui best-effort ; `{var:message}`, `{var:statut}`
  et `{var:titre}` sont toujours garantis.

## Idées plus larges (à rediscuter)
- **SSO Cloudflare centralisé** pour toute la flotte (le noyau
  `app/cloudflare_access.py` est déjà partagé, ce qui prépare le terrain).
- **Passer des variables au déclenchement depuis Home Assistant** (on reste
  « par ID pur » pour l'instant).
- **Exemples de notifications prêts à cloner** (Proxmox, HA…).

## Déjà livré (voir README pour le détail)
- Intégration **Home Assistant** (composant : boutons, capteurs, action) + clé API.
- **Aperçu live** de l'éditeur avec vraies valeurs HA + sélecteur d'entités.
- **Source dans l'historique** (Home Assistant / Proxmox / API / Manuel / Test).
- Intégration **Proxmox / PBS** (webhook natif → notif, variables, couleur auto).
- **Aide contextuelle** (« ? » → pop-up) partout, en remplacement de la page Aide.
- Authentification **Cloudflare Access** + mot de passe LAN ; **PWA** ; animations.
