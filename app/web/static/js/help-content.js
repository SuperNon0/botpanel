/* BotPanel — contenu des aides contextuelles (« ? »).
   Chaque clé = { title, html }. Le HTML supporte les encadrés .hbox et les
   blocs de code .code-block (avec bouton Copier).
   Le contenu Proxmox (URL + clé dynamiques) est construit dans l'éditeur. */
window.BP_HELP = window.BP_HELP || {};

function _cb(label, code) {
  return '<p class="help-label">' + label + '</p><div class="code-block">' +
    '<button type="button" class="copy-btn" data-copy="' +
    code.replace(/&/g, "&amp;").replace(/"/g, "&quot;") + '">Copier</button><pre>' +
    code.replace(/&/g, "&amp;").replace(/</g, "&lt;") + "</pre></div>";
}

/* ---------- Notifications ---------- */
window.BP_HELP["slug"] = {
  title: "Le slug",
  html:
    '<p>Le <b>slug</b> est l\'<b>identifiant unique</b> de la notification. C\'est lui que tu appelles pour la déclencher (Home Assistant, Proxmox, un script…).</p>' +
    '<div class="hbox hbox-tip">Minuscules, chiffres et <code>_</code> uniquement. Ex : <code>notif_porte_entree</code>, <code>backup_ovh</code>.</div>' +
    '<p>Une fois créé, garde-le stable : si tu le changes, mets à jour l\'appel côté HA / Proxmox.</p>',
};

window.BP_HELP["send_mode"] = {
  title: "Mode d'envoi",
  html:
    '<ul>' +
    '<li><b>Direct</b> — message dans le channel choisi.</li>' +
    '<li><b>Thread</b> — message dans un <b>fil</b> d\'un channel texte (regroupé par le nom du fil).</li>' +
    '<li><b>Forum</b> — message dans un <b>post</b> d\'un channel forum Discord.</li>' +
    '</ul>' +
    '<div class="hbox hbox-info">En Thread/Forum, toutes les notifs avec le même nom de fil/post vont au même endroit.</div>',
};

window.BP_HELP["list_group"] = {
  title: "Groupe (rangement du site)",
  html:
    '<p>Ce champ sert <b>uniquement à ranger</b> tes notifications dans la liste du site (par catégorie).</p>' +
    '<div class="hbox hbox-warn"><b>Aucun rapport avec Discord</b> : ça ne change pas où le message est envoyé.</div>',
};

window.BP_HELP["placeholders"] = {
  title: "Valeurs dynamiques (placeholders)",
  html:
    '<p>Insère des valeurs dans le titre, le message, les champs et le footer :</p>' +
    '<ul>' +
    '<li><code>{state:sensor.x}</code> — l\'état d\'une entité Home Assistant</li>' +
    '<li><code>{state:sensor.x|--}</code> — avec une valeur de secours si HA indispo</li>' +
    '<li><code>{attr:sensor.x:friendly_name}</code> — un attribut précis</li>' +
    '<li><code>{unit:sensor.x}</code> — l\'unité (°C, %, …)</li>' +
    '<li><code>{var:nom}</code> — une valeur envoyée au déclenchement (défaut : <code>{var:nom|--}</code>)</li>' +
    '</ul>' +
    '<div class="hbox hbox-info">L\'aperçu à droite résout les valeurs Home Assistant <b>en direct</b> quand HA est joignable. Le bouton <b>« + entité »</b> insère l\'entité choisie.</div>',
};

window.BP_HELP["buttons"] = {
  title: "Boutons",
  html:
    '<ul>' +
    '<li><b>Supprimer</b> / <b>Snooze</b> : gérés par le bot (le Snooze reporte l\'affichage N minutes).</li>' +
    '<li><b>Boutons d\'action</b> : appellent un <b>service Home Assistant</b> au clic (ex. éteindre une lumière).</li>' +
    '</ul>' +
    '<div class="hbox hbox-info">Les boutons survivent au redémarrage du bot (identifiants persistants).</div>',
};

window.BP_HELP["fields"] = {
  title: "Champs (fields)",
  html:
    '<p>Des <b>cases</b> affichées en grille dans l\'embed Discord (nom + valeur). Idéal pour présenter plusieurs infos proprement.</p>' +
    '<p>Le nom et la valeur acceptent les placeholders (<code>{state:...}</code>, <code>{var:...}</code>).</p>',
};

/* ---------- Commandes ---------- */
window.BP_HELP["commands_intro"] = {
  title: "Commandes slash",
  html:
    '<p>Tes propres commandes Discord (<code>/temperature</code>, <code>/allumer_salon</code>…) : chacune répond un message et/ou déclenche une action Home Assistant.</p>' +
    '<div class="hbox hbox-info">Toujours disponibles en plus : <code>/ha</code> (appeler n\'importe quel service HA) et <code>/clear</code> (vider un salon). Ces deux noms sont réservés.</div>' +
    '<div class="hbox hbox-tip"><b>TESTER</b> exécute la commande depuis le panel, <b>CLONER</b> en fait une copie désactivée. Discord accepte 100 commandes max.</div>',
};

window.BP_HELP["command_action"] = {
  title: "Type d'action",
  html:
    '<ul>' +
    '<li><b>service</b> — appelle <code>domaine.action</code> (ex. <code>light.turn_on</code>) avec entité + data.</li>' +
    '<li><b>script</b> — exécute un script HA (<code>script.&lt;nom&gt;</code>).</li>' +
    '<li><b>scène</b> — active une scène HA.</li>' +
    '<li><b>notification</b> — envoie une notification BotPanel par son slug.</li>' +
    '<li><b>répondre seulement</b> — aucune action, le bot répond juste (ex. afficher une température).</li>' +
    '</ul>' +
    '<div class="hbox hbox-warn">Les noms <code>ha</code> et <code>clear</code> sont réservés.</div>',
};

window.BP_HELP["command_response"] = {
  title: "Réponse d'une commande",
  html:
    '<p>Ce que le bot répond quand quelqu\'un tape la commande.</p>' +
    '<ul>' +
    '<li><b>Valeurs en direct</b> — <code>{state:sensor.temp_salon|--}</code> est remplacé par la vraie valeur au moment de la réponse (le bouton <b>+ entité</b> l\'insère pour toi).</li>' +
    '<li><b>Seulement moi / tout le salon</b> — réponse privée (éphémère) ou visible par tous.</li>' +
    '<li><b>Carte</b> — titre, couleur et grande image (ex. caméra) comme une notification.</li>' +
    '<li><b>Boutons</b> — ajoute des boutons d\'action HA sous la réponse (ex. « Éteindre »).</li>' +
    '</ul>' +
    '<div class="hbox hbox-tip">Type <b>Répondre seulement</b> : parfait pour une commande <code>/temperature</code> qui affiche juste des valeurs.</div>',
};

/* ---------- Monitoring ---------- */
window.BP_HELP["monitoring_intro"] = {
  title: "Blocs de monitoring",
  html:
    '<p><b>Un bloc = un message épinglé sur Discord</b> qui se met à jour tout seul avec les <b>vraies valeurs</b> de Home Assistant (températures, conso, état des portes…).</p>' +
    '<ul>' +
    '<li>Choisis les <b>valeurs</b> à afficher, l\'<b>intervalle</b> de rafraîchissement et le salon.</li>' +
    '<li>Ajoute des <b>boutons</b> d\'action HA sous le message (et un bouton « Actualiser »).</li>' +
    '<li><b>ACTUALISER</b> met le message à jour tout de suite.</li>' +
    '</ul>' +
    '<div class="hbox hbox-info">L\'aperçu montre les valeurs actuelles. Si le message est supprimé sur Discord, il est recréé automatiquement.</div>',
};
window.BP_HELP["monitoring_fields"] = {
  title: "Valeurs affichées",
  html:
    '<ul>' +
    '<li><b>Une entité</b> — affiche sa valeur. L\'unité HA (°C, W, %…) est ajoutée toute seule si tu laisses « Unité » vide. <b>Arrondi</b> pour éviter les 21.4567.</li>' +
    '<li><b>Attribut</b> — lit un attribut au lieu de l\'état (ex. <code>humidity</code> d\'une météo).</li>' +
    '<li><b>Texte libre</b> — combine plusieurs valeurs : <code>{state:sensor.temp|--} °C · {state:sensor.hum|--} %</code>, ou du Jinja HA.</li>' +
    '</ul>' +
    '<div class="hbox hbox-info">L\'aperçu montre les <b>vraies valeurs</b> actuelles de Home Assistant.</div>',
};
window.BP_HELP["monitoring_interval"] = {
  title: "Intervalle de rafraîchissement",
  html:
    '<p>Le message épinglé se met à jour tout seul à cet intervalle (température, conso…).</p>' +
    '<div class="hbox hbox-warn">Minimum <b>30 secondes</b>. Si le message est supprimé sur Discord, il est recréé automatiquement.</div>',
};

window.BP_HELP["notif_intro"] = {
  title: "Notification",
  html:
    '<p>Un message Discord que Home Assistant (ou un webhook) déclenche par son <code>slug</code>.</p>' +
    '<div class="hbox hbox-tip">Modes d\'envoi, placeholders, groupes… tout est détaillé sur la <a href="/aide">page Aide</a>.</div>',
};

/* ---------- Paramètres ---------- */
window.BP_HELP["integration_key"] = {
  title: "Clé API",
  html:
    '<p>Clé secrète qui permet au <b>module Home Assistant</b>, aux <b>webhooks Proxmox</b> et à <b>Claude (MCP)</b> de se connecter à BotPanel (en-tête <code>X-API-Key</code>).</p>' +
    '<div class="hbox hbox-tip"><b>Home Assistant</b> : colle-la à l\'ajout de l\'intégration BotPanel (URL + clé).<br><b>Proxmox</b> : dans l\'en-tête du webhook.<br><b>Claude</b> : dans le connecteur (voir le « ? » du bloc Claude).</div>' +
    '<div class="hbox hbox-info">Masquée par défaut : <b>👁 Afficher</b> pour la voir, <b>Copier</b> pour la copier sans l\'afficher.</div>' +
    '<div class="hbox hbox-warn"><b>Régénérer</b> invalide l\'ancienne clé : il faudra la remettre partout (HA, Proxmox, Claude).</div>' +
    '<div class="hbox hbox-info">Les webhooks simples (<code>/api/notify</code>) fonctionnent <b>sans</b> cette clé.</div>',
};

window.BP_HELP["ha_integration"] = {
  title: "Intégration Home Assistant",
  html:
    '<p>Le <b>module BotPanel pour Home Assistant</b> ajoute des boutons, des capteurs et une action pour envoyer tes notifications depuis HA.</p>' +
    '<ul><li><b>HA joignable</b> : BotPanel arrive à parler à Home Assistant.</li>' +
    '<li><b>Module connecté</b> : dernière fois que le module HA a contacté BotPanel (vert = il y a moins de 5 min).</li></ul>' +
    '<div class="hbox hbox-tip">Installation : dossier <code>custom_components/botpanel/</code> du dépôt (compatible HACS), puis ajoute l\'intégration avec l\'URL de BotPanel + la <b>Clé API</b>.</div>',
};

window.BP_HELP["home_url"] = {
  title: "URL d'accueil",
  html:
    '<p>Depuis la page d\'<b>accueil</b>, un clic sur le logo t\'envoie vers cette adresse (ex. ton Home Assistant, ton NAS…).</p>' +
    '<div class="hbox hbox-info">Depuis les autres pages, le logo ramène toujours à l\'accueil.</div>',
};

window.BP_HELP["update"] = {
  title: "Mise à jour",
  html:
    '<p>Récupère la dernière version (<code>git pull</code>), réinstalle les dépendances puis redémarre le service. La page se recharge toute seule au retour du bot.</p>' +
    '<div class="hbox hbox-tip">Aussi possible depuis Claude avec les outils MCP <code>check_update</code> / <code>update_site</code> (avec point de retour arrière).</div>',
};

window.BP_HELP["color_presets"] = {
  title: "Couleurs préconfigurées",
  html:
    '<p>Ces couleurs apparaissent en <b>pastilles</b> dans les éditeurs (notifications, commandes, monitoring) : un clic applique la couleur.</p>' +
    '<div class="hbox hbox-tip">Donne-leur un nom parlant (<i>Alerte porte</i>, <i>Info confort</i>). Tu peux aussi en créer une depuis un éditeur avec la pastille <b>＋</b>.</div>',
};

window.BP_HELP["fav_channels"] = {
  title: "Channels favoris",
  html:
    '<p>Tes channels les plus utilisés, avec un nom parlant. Ils apparaissent <b>en tête (★)</b> dans la liste des channels de chaque éditeur.</p>' +
    '<div class="hbox hbox-tip">Le plus simple : bouton <b>★ Favori</b> sur un channel de la liste « détectés ». Sinon, ajoute un ID à la main (clic droit sur le salon → Copier l\'identifiant).</div>',
};

window.BP_HELP["forums"] = {
  title: "Channels forum",
  html:
    '<p>Channels de type <b>Forum</b> vus par le bot : utilisables comme destination en mode <b>Forum</b> d\'une notification (un post par groupe).</p>' +
    '<div class="hbox hbox-warn">Le bot doit avoir la permission <b>Send Messages in Threads</b> sur ces channels.</div>',
};

window.BP_HELP["threads"] = {
  title: "Fils et posts actifs",
  html:
    '<p>Quand une notification est en mode <b>Thread</b> ou <b>Forum</b>, elle est rangée dans un fil (ou post) portant le nom de son groupe. La liste montre ceux que BotPanel a créés.</p>' +
    '<div class="hbox hbox-tip"><b>Réinitialiser</b> force la création d\'un nouveau fil au prochain envoi — utile si tu l\'as supprimé à la main sur Discord.</div>',
};

window.BP_HELP["cf_access"] = {
  title: "Cloudflare Access",
  html:
    '<p>Permet de te connecter <b>sans mot de passe</b> quand tu passes par <b>Cloudflare Access</b> (ton e-mail est déjà vérifié).</p>' +
    '<ul><li><b>Équipe</b> : le nom seul (ex. <code>super-nono</code>), pas l\'URL complète.</li>' +
    '<li><b>AUD</b> : le « Application Audience Tag » de ton app Access.</li></ul>' +
    '<div class="hbox hbox-ok">BotPanel <b>vérifie le badge signé</b> (JWT) : impossible de se faire passer pour Cloudflare en local.</div>' +
    '<div class="hbox hbox-warn"><b>Accès local décoché</b> = uniquement via Cloudflare : tout accès direct est refusé (403). Ne le décoche que si le serveur est injoignable hors Cloudflare, sinon tu risques de te bloquer dehors.</div>' +
    '<p class="help-label">Résultat du bouton « Tester »</p>' +
    '<ul><li><b>non testé</b> : aucun badge reçu (tu n\'es pas passé par Cloudflare).</li>' +
    '<li>Erreur <b>audience</b> : l\'AUD ne correspond pas à l\'app Access.</li>' +
    '<li>Erreur <b>…cloudflareaccess.com…</b> : mets le <b>nom seul</b> dans Équipe.</li></ul>',
};

window.BP_HELP["password"] = {
  title: "Mot de passe",
  html:
    '<p>Protection <b>optionnelle</b> par mot de passe (compte unique <code>admin</code>) pour l\'accès local. Sans protection, le panel est ouvert à tout ton réseau.</p>' +
    '<ul><li><b>Activer / changer / désactiver</b> ici même (6 caractères minimum).</li>' +
    '<li><b>Mot de passe oublié</b> : sur le serveur →</li></ul>' +
    _cb("Réinitialisation (serveur)", "sudo bash /opt/botpanel/deploy/reset_admin.sh \"nouveau-mot-de-passe\"") +
    '<div class="hbox hbox-info">Les routes machine (<code>/api/notify</code>, webhooks) restent toujours ouvertes.</div>',
};

window.BP_HELP["backup"] = {
  title: "Sauvegarde & migration",
  html:
    '<ul>' +
    '<li><b>Exporter</b> : télécharge un fichier JSON avec toute ta configuration (notifications, commandes, monitoring, couleurs, channels…).</li>' +
    '<li><b>Importer</b> : recharge ce fichier, pour restaurer une sauvegarde ou passer sur une nouvelle instance de BotPanel.</li>' +
    '</ul>' +
    '<div class="hbox hbox-warn">L\'import <b>remplace</b> toute la configuration actuelle. L\'historique et les états Discord ne sont ni exportés ni touchés.</div>',
};

/* ---------- Setup (assistant) ---------- */
window.BP_HELP["discord_token"] = {
  title: "Token du bot Discord",
  html:
    '<p>Crée une application sur le <b>Discord Developer Portal</b> → onglet <b>Bot</b> → <b>Reset Token</b> → <b>Copy</b>.</p>' +
    '<div class="hbox hbox-warn">Garde ce token <b>secret</b>. Aucun « intent privilégié » n\'est nécessaire.</div>' +
    '<p>Invite le bot via <b>OAuth2 → URL Generator</b> (scopes <code>bot</code> + <code>applications.commands</code>), permissions : Send Messages, Embed Links, Manage Messages, Read Message History, Create/Send/Manage Threads.</p>',
};

window.BP_HELP["discord_ids"] = {
  title: "IDs serveur & channels",
  html:
    '<p>Active le <b>mode développeur</b> Discord (Paramètres → Avancés), puis <b>clic droit → Copier l\'identifiant</b> :</p>' +
    '<ul><li><b>Serveur</b> : clic droit sur l\'icône du serveur.</li>' +
    '<li><b>Channel par défaut</b> : clic droit sur le salon des notifications.</li>' +
    '<li><b>Channel monitoring</b> : idem sur le salon de suivi.</li></ul>' +
    '<div class="hbox hbox-info">Les IDs sont de longs nombres, ex. <code>123456789012345678</code>.</div>',
};

window.BP_HELP["ha_token"] = {
  title: "Home Assistant (URL + token)",
  html:
    '<p><b>URL</b> : l\'adresse locale de HA, ex. <code>http://192.168.1.x:8123</code>.</p>' +
    '<p><b>Token</b> : dans HA → <b>profil → Sécurité → Jetons d\'accès longue durée → Créer</b>, puis copie-le.</p>' +
    '<div class="hbox hbox-tip">Le token permet à BotPanel de lire les états et d\'appeler des services HA.</div>',
};

/* ---------- API (déclencher depuis un projet) ---------- */
window.BP_HELP["api_usage"] = {
  title: "Déclencher une notif depuis un projet (API)",
  html:
    '<p>Tu crées la notif <b>ici</b> (avec un slug), et n\'importe quel projet la déclenche par une simple requête HTTP.</p>' +
    _cb("Requête", "POST http://IP_BOTPANEL:8080/api/notify\nContent-Type: application/json\n\n{ \"id\": \"backup_done\" }") +
    '<p>Avec du texte qui change, mets des <code>{var:nom}</code> dans la notif et envoie les valeurs :</p>' +
    _cb("Avec variables", "{ \"id\": \"backup_done\",\n  \"vars\": { \"vmid\": \"100\", \"duree\": \"2m34s\" } }") +
    '<div class="hbox hbox-ok">Cette route reste <b>toujours accessible</b>, même avec la protection par mot de passe : tes projets ne sont jamais bloqués.</div>' +
    '<div class="hbox hbox-info">Guide complet (Python, Node, PHP, Bash) : <code>docs/API.md</code>.</div>',
};

/* ---------- Serveur MCP (piloter BotPanel depuis Claude) ---------- */
window.BP_HELP["mcp"] = {
  title: "Serveur MCP — piloter BotPanel depuis Claude",
  html:
    '<p>Le <b>serveur MCP</b> connecte BotPanel à <b>Claude</b> (claude.ai, app Claude ou Claude Desktop). Une fois branché, <b>Claude peut agir sur BotPanel</b> : lister, déclencher et créer des notifications, envoyer un message ponctuel, lire l\'état et l\'historique.</p>' +
    '<div class="hbox hbox-tip"><b>Exemple :</b> « Claude, crée une notif qui prévient quand la porte du garage s\'ouvre » → Claude lit l\'entité dans Home Assistant <b>et</b> crée la notif dans BotPanel, en direct.</div>' +
    '<p class="help-label">1) L\'URL et la clé</p>' +
    '<p>L\'<b>URL</b> est affichée dans le bloc. La clé = la <b>Clé API</b> du bloc du dessus (la même que Home Assistant / Proxmox, masquée par défaut : bouton 👁 Afficher). Deux façons de la présenter :</p>' +
    '<ul>' +
    '<li><b>En-tête</b> <code>Authorization: Bearer &lt;clé&gt;</code> ou <code>X-API-Key: &lt;clé&gt;</code> (recommandé)</li>' +
    '<li><b>Dans l\'URL</b> : <code>.../mcp/&lt;clé&gt;</code> (si le client ne gère pas les en-têtes — la clé apparaît alors dans les logs)</li>' +
    '</ul>' +
    '<p class="help-label">2) Connexion depuis claude.ai / app Claude</p>' +
    '<div class="hbox hbox-warn"><b>Important — Cloudflare :</b> le site est protégé par Cloudflare Access (login). Claude vient d\'Internet, il faut donc <b>ouvrir le chemin <code>/mcp</code> dans Cloudflare Zero Trust</b> (Access → Applications → app sur le path <code>mcp</code> → policy <b>Bypass / Everyone</b>). BotPanel garde la protection par clé API. Détails dans <code>docs/MCP.md</code>.</div>' +
    '<div class="hbox hbox-info">Réglages → <b>Connecteurs</b> → <b>Ajouter un connecteur personnalisé</b> → colle l\'URL. Si on te demande une auth, mets <code>Authorization = Bearer &lt;clé&gt;</code> ; sinon utilise l\'<b>URL avec la clé incluse</b>.</div>' +
    '<p class="help-label">3) Connexion depuis Claude Desktop</p>' +
    _cb("claude_desktop_config.json", '{\n  "mcpServers": {\n    "botpanel": {\n      "command": "npx",\n      "args": ["mcp-remote", "https://TON-DOMAINE/mcp",\n               "--header", "Authorization: Bearer TA_CLE"]\n    }\n  }\n}') +
    '<p class="help-label">Ce que Claude peut faire</p>' +
    '<ul>' +
    '<li><code>list_notifications</code> — lister tes notifications</li>' +
    '<li><code>send_notification</code> — déclencher une notif (par slug + variables)</li>' +
    '<li><code>create_notification</code> — créer une nouvelle notif</li>' +
    '<li><code>send_quick_message</code> — envoyer un message ponctuel sur Discord</li>' +
    '<li><code>get_state</code> — état (bot en ligne, envois, dernière alerte)</li>' +
    '<li><code>list_history</code> — derniers envois</li>' +
    '</ul>' +
    '<div class="hbox hbox-warn">Route <b>machine</b> protégée uniquement par la clé API. Si tu régénères la clé, remets-la à jour dans le connecteur Claude.</div>' +
    '<div class="hbox hbox-info">Guide complet : <code>docs/MCP.md</code>.</div>',
};
