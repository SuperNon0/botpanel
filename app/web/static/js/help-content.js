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
window.BP_HELP["command_action"] = {
  title: "Type d'action",
  html:
    '<ul>' +
    '<li><b>service</b> — appelle <code>domaine.action</code> (ex. <code>light.turn_on</code>) avec entité + data.</li>' +
    '<li><b>script</b> — exécute un script HA (<code>script.&lt;nom&gt;</code>).</li>' +
    '<li><b>scène</b> — active une scène HA.</li>' +
    '<li><b>notification</b> — envoie une notification BotPanel par son slug.</li>' +
    '</ul>' +
    '<div class="hbox hbox-warn">Les noms <code>ha</code> et <code>clear</code> sont réservés.</div>',
};

/* ---------- Monitoring ---------- */
window.BP_HELP["monitoring_interval"] = {
  title: "Intervalle de rafraîchissement",
  html:
    '<p>Le message épinglé se met à jour tout seul à cet intervalle (température, conso…).</p>' +
    '<div class="hbox hbox-warn">Minimum <b>30 secondes</b>. Si le message est supprimé sur Discord, il est recréé automatiquement.</div>',
};

/* ---------- Paramètres ---------- */
window.BP_HELP["integration_key"] = {
  title: "Clé API (intégration)",
  html:
    '<p>Cette clé sert au <b>module Home Assistant</b> et aux <b>webhooks Proxmox</b> pour se connecter à BotPanel en toute sécurité (en-tête <code>X-API-Key</code>).</p>' +
    '<div class="hbox hbox-tip"><b>Home Assistant</b> : copie cette clé lors de l\'ajout de l\'intégration BotPanel (URL + clé).<br><b>Proxmox</b> : mets-la dans l\'en-tête du webhook.</div>' +
    '<div class="hbox hbox-warn"><b>Régénérer</b> invalide l\'ancienne clé : il faudra la remettre à jour côté HA / Proxmox.</div>' +
    '<div class="hbox hbox-info">Les webhooks existants (<code>/api/notify</code>) continuent de fonctionner <b>sans</b> cette clé.</div>',
};

window.BP_HELP["cf_access"] = {
  title: "Cloudflare / Accès",
  html:
    '<p>Permet de te connecter <b>sans mot de passe</b> quand tu passes par <b>Cloudflare Access</b> (ton e-mail Google est déjà vérifié).</p>' +
    '<ul><li><b>Équipe</b> : le nom seul (ex. <code>super-nono</code>).</li>' +
    '<li><b>AUD</b> : le « Application Audience Tag » de ton app Access.</li></ul>' +
    '<div class="hbox hbox-ok">BotPanel <b>vérifie le badge signé</b> (JWT) : impossible de se faire passer pour Cloudflare en local.</div>' +
    '<div class="hbox hbox-warn">« Accès uniquement Cloudflare » = tout accès direct (sans badge) est refusé. À n\'activer que si l\'origine est injoignable hors Cloudflare.</div>',
};

window.BP_HELP["password"] = {
  title: "Compte & sécurité (mot de passe)",
  html:
    '<p>Protection <b>optionnelle</b> par mot de passe (compte unique <code>admin</code>) pour l\'accès local.</p>' +
    '<ul><li><b>Activer / changer / désactiver</b> ici même.</li>' +
    '<li><b>Mot de passe oublié</b> : sur le serveur →</li></ul>' +
    _cb("Réinitialisation (serveur)", "sudo bash /opt/botpanel/deploy/reset_admin.sh \"nouveau-mot-de-passe\"") +
    '<div class="hbox hbox-info">Les routes machine (<code>/api/notify</code>) restent toujours ouvertes.</div>',
};

window.BP_HELP["backup"] = {
  title: "Sauvegarde & migration",
  html:
    '<ul>' +
    '<li><b>Exporter</b> : télécharge un JSON de toute ta configuration (notifs, commandes, monitoring, presets).</li>' +
    '<li><b>Importer</b> : recharge ce fichier sur une nouvelle instance.</li>' +
    '</ul>' +
    '<div class="hbox hbox-warn">L\'import <b>remplace</b> la configuration existante (l\'historique et les états Discord ne sont pas touchés).</div>',
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
