# Feuille de route — V2 BotPanel

> Notes de cadrage pour la V2. Rien ici n'est implémenté : ce sont les
> fonctionnalités à développer **quand la V2 sera lancée**.

## 1. Intégration Home Assistant (cœur de la V2)

Objectif : exposer BotPanel dans Home Assistant **sans jamais pousser de valeurs
depuis HA** — toute la configuration reste sur BotPanel (c'est le principe voulu).

- **Notifications comme entités HA** : chaque notification BotPanel apparaît côté
  HA (état / disponibilité), pour pouvoir la déclencher depuis une automatisation.
- **Action (service) avec autocomplétion** : une action HA « envoyer une
  notification BotPanel » qui propose la liste des notifications existantes
  (autocomplete), déclenchée par `id`/slug.
- **Sens unique** : HA *déclenche* des notifications déjà configurées dans
  BotPanel ; HA ne *modifie* ni n'*envoie* aucune configuration/valeur vers
  BotPanel. (Décision explicite de l'utilisateur.)

## 2. Sécurité machine — clé API sur les routes appelées par des machines

Aujourd'hui `/api/notify` (webhooks HA/Proxmox) est **ouverte**, protégée
uniquement par le réseau (LAN / origine derrière Cloudflare). À durcir en V2 :

- **Clé API optionnelle** (en-tête type `X-API-Key`) sur `/api/notify` et les
  futurs webhooks/endpoints machine de l'intégration HA.
- **Jamais** de login humain sur ces routes : elles restent hors du garde
  d'authentification (`_AUTH_PUBLIC_PREFIXES`), la clé API + le LAN suffisent.
- À faire **en même temps** que l'intégration HA (on définit d'un coup comment HA
  s'authentifie auprès de BotPanel).

## 3. Idée plus large (à rediscuter) — SSO Cloudflare centralisé pour la flotte

- Un seul point d'entrée Cloudflare Access pour tous les sites (BotPanel,
  FuelLog, Site-base…), chacun restant un programme séparé qui lit le **même
  badge** signé. Le noyau `cloudflare_access.py` est déjà partagé/identique entre
  les sites, ce qui prépare le terrain.

---

*Créé pendant la mise en place de l'auth Cloudflare + thème partagé. À reprendre
au démarrage de la V2.*
