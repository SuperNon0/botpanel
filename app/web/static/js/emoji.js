// Emoji picker reutilisable.
// Usage: openEmojiPicker((emoji) => { /* insert emoji */ });
//
// Liste curee : icones utiles pour notifications HA / monitoring.

const EMOJI_GROUPS = {
  "Maison": ["🏠","🏡","🛋️","🛏️","🛁","🚪","🪟","🪜","🪑","🚽","🪞","🧺","🧻","🧹","🧼"],
  "Confort": ["🌡️","💧","💨","☀️","🌙","🌤️","⛅","🌧️","⛈️","❄️","🔥","🌬️","☁️","🌫️"],
  "Eclairage": ["💡","🔦","🕯️","🌟","✨","💫","🪔","🌞","🌝"],
  "Securite": ["🔒","🔓","🔐","🔑","🗝️","🚨","⚠️","🛡️","👁️","🚫","✅","❌","🔔","🔕"],
  "Cuisine": ["🍳","☕","🫖","🍷","🍕","🍔","🥗","🥖","🍞","🥞","🍰","🍪","🥄","🍴"],
  "Energie": ["⚡","🔋","🔌","♻️","🌱","🌍","💰","📊","📈","📉","💧","🌊"],
  "Tech": ["📱","💻","🖥️","⌨️","🖱️","📺","🎮","📷","📸","🎤","🎧","🔊","🔇","📡"],
  "Statut": ["✅","❌","⭕","🟢","🟡","🟠","🔴","🔵","🟣","⚫","⚪","🟤","🆗","🆘"],
  "Vehicules": ["🚗","🚙","🛵","🚲","🛴","⛽","🚏","🅿️","🚦","🚧"],
  "Calendrier": ["📅","📆","⏰","⏲️","⌛","⏳","🕐","🕑","🕒","🕓","🕔","🕕","🕖","🕗"],
  "Personnes": ["👤","👥","🧑","👩","👨","👶","🧒","👵","👴","🤖","👻","🐶","🐱"],
  "Symboles": ["⭐","💯","💢","💥","💦","💤","🎉","🎊","🎈","🎁","💌","📌","📍","🏷️"],
};

let _emojiPicker = null;

function _buildEmojiPicker() {
  const modal = document.createElement("div");
  modal.className = "ent-modal";
  modal.id = "emoji-modal";
  modal.innerHTML = `
    <div class="ent-modal-box">
      <div class="ent-modal-head">
        <strong>Choisir une icone</strong>
        <button type="button" class="btn btn-secondary btn-small" id="emoji-close">Fermer</button>
      </div>
      <input type="text" class="form-input" id="emoji-search" placeholder="Filtrer par categorie...">
      <div class="emoji-grid" id="emoji-grid"></div>
      <div class="form-hint" style="margin-top:0.5rem;">
        Tu peux aussi coller n'importe quel emoji directement dans le champ.
      </div>
    </div>
  `;
  document.body.appendChild(modal);
  return modal;
}

function _renderEmojiGroups(filter) {
  const grid = document.getElementById("emoji-grid");
  const q = (filter || "").trim().toLowerCase();
  const html = [];
  for (const [group, emojis] of Object.entries(EMOJI_GROUPS)) {
    if (q && !group.toLowerCase().includes(q)) continue;
    html.push(`<div class="emoji-group-name">${esc(group)}</div>`);
    html.push(`<div class="emoji-group">`);
    for (const e of emojis) {
      html.push(`<button type="button" class="emoji-btn" data-e="${esc(e)}">${e}</button>`);
    }
    html.push(`</div>`);
  }
  grid.innerHTML = html.join("");
}

function openEmojiPicker(onPick) {
  if (!_emojiPicker) {
    _emojiPicker = _buildEmojiPicker();
    document.getElementById("emoji-close").addEventListener("click", closeEmojiPicker);
    _emojiPicker.addEventListener("click", (e) => {
      if (e.target === _emojiPicker) closeEmojiPicker();
    });
    document.getElementById("emoji-search").addEventListener("input", (e) => {
      _renderEmojiGroups(e.target.value);
    });
    document.getElementById("emoji-grid").addEventListener("click", (e) => {
      const btn = e.target.closest(".emoji-btn");
      if (!btn) return;
      if (_emojiPickerCallback) _emojiPickerCallback(btn.dataset.e);
      closeEmojiPicker();
    });
  }
  _emojiPickerCallback = onPick;
  _renderEmojiGroups("");
  _emojiPicker.classList.add("open");
  setTimeout(() => document.getElementById("emoji-search").focus(), 50);
}

let _emojiPickerCallback = null;

function closeEmojiPicker() {
  if (_emojiPicker) _emojiPicker.classList.remove("open");
  _emojiPickerCallback = null;
}

// Helper : insere un emoji dans un input/textarea a la position du curseur
function insertAtCursor(el, text) {
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? el.value.length;
  el.value = el.value.slice(0, start) + text + el.value.slice(end);
  el.selectionStart = el.selectionEnd = start + text.length;
  el.focus();
  el.dispatchEvent(new Event("input", { bubbles: true }));
}
