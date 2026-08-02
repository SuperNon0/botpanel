# Guide — construire une page d'aide claire (pattern réutilisable)

Ce document explique comment est construite la page **Aide** de BotPanel, pour
qu'un développeur puisse reproduire le même genre de page dans un autre projet.

Le principe est **indépendant du langage/framework** : c'est du HTML + CSS. Un
exemple complet et autonome est fourni à la fin (à copier dans un fichier `.html`
et à ouvrir directement dans un navigateur).

---

## 1. Le problème, et l'idée

Une page d'aide devient vite un **mur de texte en vrac** : tout est affiché, on ne
sait pas où regarder. L'idée pour la rendre agréable :

1. **Ranger par thèmes** — 3 à 5 grandes catégories, pas 15 titres à plat.
2. **Navigation rapide en haut** — une rangée de cartes cliquables (une par thème)
   qui amènent directement à la bonne section.
3. **Tout replié par défaut (accordéons)** — chaque sujet est un bloc `<details>`
   fermé ; on ne déplie que ce dont on a besoin. C'est **ça** qui supprime le vrac.
4. **Une section mise en avant** — la fonctionnalité la plus importante n'est PAS
   repliée et est stylée différemment (bordure colorée, étapes numérotées).

---

## 2. La structure

```
Titre + sous-titre
│
├─ Barre de navigation (grille de cartes : 🚀 Thème 1, 🔔 Thème 2, …)
│
├─ ## Thème 1  (titre de catégorie avec ancre #theme1)
│   ├─ <details> Sujet A (replié)
│   ├─ <details> Sujet B (replié)
│   └─ …
│
├─ ## Thème 2
│   └─ …
│
├─ ## Thème « mis en avant »   ← bloc ouvert, stylé, étapes 1-2-3
│
└─ ## Thème N
    └─ <details> …
```

Chaque **titre de catégorie** a un `id` (ex. `id="theme1"`) ; chaque **carte de
navigation** est un lien `href="#theme1"`. Le CSS `scroll-margin-top` évite que le
titre se colle en haut de l'écran.

---

## 3. Les 4 briques de code

| Brique | Élément | Rôle |
|--------|---------|------|
| Navigation | grille de `<a href="#…">` | sauter à un thème |
| Titre de catégorie | `<h2 id="…">` | séparer les grands blocs |
| Sujet | `<details><summary>…</summary>…</details>` | replié/dépliable, **zéro JS** |
| Mise en avant | `<div>` stylé + étapes numérotées | attirer l'œil sur l'essentiel |

Les accordéons `<details>`/`<summary>` sont **natifs** : pas besoin de JavaScript.

---

## 4. Exemple complet (à copier dans un fichier `.html`)

Cet exemple est autonome, thème sombre/clair automatique, et reproduit le même
rendu. Le dev n'a qu'à remplacer le contenu et ajuster les couleurs (variables CSS
en haut).

```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aide</title>
<style>
  :root {
    --bg: #f5f5f7; --surface: #fff; --text: #1a1b22; --dim: #6b6d7e;
    --border: #e5e5ee; --accent: #e8c547; --code-bg: #f0f0f4;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #121218; --surface: #1a1c24; --text: #ececf2; --dim: #9294a6;
      --border: #292b38; --accent: #e8c547; --code-bg: #12131a;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: system-ui, sans-serif; line-height: 1.6;
  }
  .wrap { max-width: 860px; margin: 0 auto; padding: 2rem 1.2rem; }
  h1 { margin: 0 0 0.3rem; }
  .sub { color: var(--dim); margin: 0 0 1.6rem; }

  /* 1. Navigation par thèmes */
  .nav { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px,1fr)); gap: 0.8rem; margin-bottom: 1.8rem; }
  .nav a {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1rem; text-decoration: none; color: var(--text);
    transition: border-color .15s, transform .15s;
  }
  .nav a:hover { border-color: var(--accent); transform: translateY(-2px); }
  .nav .emoji { font-size: 1.4rem; display: block; }
  .nav .t { font-weight: 600; display: block; margin-top: .3rem; }
  .nav .d { color: var(--dim); font-size: .8rem; }

  /* 2. Titre de catégorie */
  .cat { margin: 2rem 0 .8rem; padding-bottom: .4rem; border-bottom: 1px solid var(--border); scroll-margin-top: 1rem; }

  /* 3. Accordéon (sujet) */
  details {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 0 1rem; margin-bottom: .7rem;
  }
  summary { cursor: pointer; font-weight: 600; padding: 1rem 0; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  summary::before { content: "▸ "; color: var(--dim); }
  details[open] summary::before { content: "▾ "; }
  details > *:not(summary) { margin-top: 0; }
  details p, details ul { margin: .3rem 0 1rem; }

  /* 4. Bloc mis en avant */
  .highlight { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 12px; padding: 1.2rem 1.4rem; }
  .steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: .8rem; margin: 1rem 0; }
  .step { display: flex; gap: .7rem; background: color-mix(in srgb, var(--text) 4%, transparent); border-radius: 10px; padding: .8rem; }
  .num { flex: none; width: 26px; height: 26px; border-radius: 50%; background: var(--accent); color: #1a1a1a; font-weight: 700; display: grid; place-items: center; }

  code, pre { background: var(--code-bg); border-radius: 6px; }
  code { padding: .1rem .35rem; font-size: .9em; }
  pre { padding: .8rem 1rem; overflow-x: auto; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Aide</h1>
  <p class="sub">Clique sur un thème pour le déplier</p>

  <!-- 1. Navigation -->
  <div class="nav">
    <a href="#demarrage"><span class="emoji">🚀</span><span class="t">Démarrage</span><span class="d">Installer & configurer</span></a>
    <a href="#usage"><span class="emoji">🔔</span><span class="t">Utilisation</span><span class="d">Les fonctions au quotidien</span></a>
    <a href="#api"><span class="emoji">🔌</span><span class="t">API</span><span class="d">Intégrer un projet</span></a>
  </div>

  <!-- 2. Catégorie -->
  <h2 class="cat" id="demarrage">🚀 Démarrage</h2>

  <!-- 3. Sujets (accordéons repliés) -->
  <details>
    <summary>Première étape</summary>
    <p>Explication de la première étape. Reste court et concret.</p>
    <ol><li>Fais ceci</li><li>Puis cela</li></ol>
  </details>
  <details>
    <summary>Deuxième étape</summary>
    <p>Autre explication…</p>
  </details>

  <h2 class="cat" id="usage">🔔 Utilisation</h2>
  <details>
    <summary>Une fonctionnalité</summary>
    <p>Ce qu'elle fait, avec un exemple : <code>exemple</code>.</p>
  </details>

  <!-- 4. Section mise en avant (non repliée) -->
  <h2 class="cat" id="api">🔌 API</h2>
  <div class="highlight">
    <p><strong>L'idée en une phrase :</strong> explique le concept clé simplement.</p>
    <div class="steps">
      <div class="step"><span class="num">1</span><div><strong>Étape 1</strong><br>courte description</div></div>
      <div class="step"><span class="num">2</span><div><strong>Étape 2</strong><br>courte description</div></div>
      <div class="step"><span class="num">3</span><div><strong>Étape 3</strong><br>courte description</div></div>
    </div>
    <pre>POST /exemple
{ "clef": "valeur" }</pre>
  </div>
</div>
</body>
</html>
```

---

## 5. Comment l'adapter

- **Contenu** : remplace les thèmes, les `<summary>` et les textes. Garde 3–5 thèmes max.
- **Couleurs** : change les variables CSS en haut (`--accent`, `--bg`, `--surface`…).
  Le thème clair/sombre suit automatiquement le système via `prefers-color-scheme`.
- **Intégration** : ce n'est que du HTML/CSS — ça se colle dans n'importe quelle page
  (React, Vue, Jinja, PHP, statique…). Aucune dépendance, aucun JavaScript.
- **Règle d'or** : mets **une seule** section en avant (la plus importante), tout le
  reste en accordéon fermé. C'est ce contraste qui rend la page lisible.

---

## 6. Check-list

- [ ] 3 à 5 grandes catégories, pas plus.
- [ ] Une barre de navigation en cartes en haut.
- [ ] Chaque sujet dans un `<details>` **fermé** par défaut.
- [ ] La fonctionnalité clé mise en avant (ouverte, bordure colorée, étapes 1-2-3).
- [ ] Thème clair **et** sombre gérés (variables CSS + `prefers-color-scheme`).
- [ ] Textes courts et concrets, avec des exemples.
