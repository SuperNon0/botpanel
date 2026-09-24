/* BotPanel — contenu des aides contextuelles (« ? »).
   Chaque clé = { title, html }. Le HTML supporte les encadrés .hbox et les
   blocs de code .code-block (avec bouton Copier).
   Le contenu Proxmox (URL + clé dynamiques) est construit dans l'éditeur. */
window.BP_HELP = window.BP_HELP || {};

window.BP_HELP["slug"] = {
  title: "Le slug",
  html:
    '<p>Le <b>slug</b> est l\'<b>identifiant unique</b> de la notification. C\'est lui que tu appelles pour la déclencher (depuis Home Assistant, Proxmox, un script…).</p>' +
    '<div class="hbox hbox-tip">Minuscules, chiffres et <code>_</code> uniquement. Ex : <code>notif_porte_entree</code>, <code>backup_ovh</code>.</div>' +
    '<p>Une fois créé, garde-le stable : si tu le changes, pense à mettre à jour l\'appel côté HA / Proxmox.</p>',
};

window.BP_HELP["placeholders"] = {
  title: "Variables & placeholders",
  html:
    '<p>Tu peux insérer des <b>valeurs dynamiques</b> dans le titre, le message, les champs et le footer :</p>' +
    '<ul>' +
    '<li><code>{state:sensor.x}</code> — l\'état d\'une entité Home Assistant</li>' +
    '<li><code>{attr:sensor.x:friendly_name}</code> — un attribut d\'entité</li>' +
    '<li><code>{unit:sensor.x}</code> — l\'unité (°C, %, …)</li>' +
    '<li><code>{{ states(\'sensor.x\') }}</code> — un template Jinja Home Assistant</li>' +
    '<li><code>{var:nom}</code> — une valeur envoyée au déclenchement (avec défaut : <code>{var:nom|--}</code>)</li>' +
    '</ul>' +
    '<div class="hbox hbox-info">L\'aperçu à droite résout les valeurs Home Assistant <b>en direct</b> quand HA est joignable.</div>',
};
