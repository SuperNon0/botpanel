/* BotPanel — briques partagees des editeurs (notifications, commandes, monitoring).
   - rendu Markdown Discord + utilitaires couleur/date
   - selecteur d'entites Home Assistant (modal groupee par domaine)
   - presets de couleurs en pastilles (+ creation d'un preset depuis l'editeur)
   - liste deroulante des channels Discord
   - constructeur de boutons d'action HA
   - listes repliables par groupe (pages liste) */

// ============================================================
// Utilitaires
// ============================================================
function renderDiscordMd(text) {
  let html = esc(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__(.+?)__/g, "<u>$1</u>");
  html = html.replace(/~~(.+?)~~/g, "<s>$1</s>");
  html = html.replace(/`([^`]+?)`/g, "<code>$1</code>");
  html = html.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
  return html;
}

function colorToHex(n) {
  return "#" + ((n || 0) & 0xFFFFFF).toString(16).padStart(6, "0");
}
function hexToInt(h) {
  return parseInt((h || "#000000").replace("#", ""), 16);
}

function formatTsFr(d) {
  const months = ["janvier","fevrier","mars","avril","mai","juin",
                  "juillet","aout","septembre","octobre","novembre","decembre"];
  const pad = n => String(n).padStart(2, "0");
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()} a ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// Couleurs des boutons Discord (apercu)
const STYLE_BG = {
  primary: "#5865f2", secondary: "#4e5058",
  success: "#248046", danger: "#da373c",
};
const STYLE_LABEL = {
  primary: "Bleu", secondary: "Gris", success: "Vert", danger: "Rouge",
};

// Detecte un placeholder HA ({state:..}, {attr:..}, {unit:..}) ou du Jinja HA.
const HA_PLACEHOLDER_RE = /\{(state|attr|unit):|\{\{|\{%/;
function hasHaPlaceholder(...parts) {
  return parts.some(s => HA_PLACEHOLDER_RE.test(s || ""));
}

// Voyant d'etat de l'apercu (valeurs HA en direct / HA injoignable)
function setResolveStatus(el, kind) {
  if (!el) return;
  el.textContent =
    kind === "ok"      ? "🟢 valeurs Home Assistant en direct" :
    kind === "loading" ? "⏳ récupération…" :
    kind === "err"     ? "🔴 Home Assistant injoignable" :
                         "⚪ aucune entité HA";
}

// Lance `fn` apres `ms` sans nouvel appel (frappe clavier).
function debounce(fn, ms) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// Boutons de l'apercu Discord
function previewButtonsHtml(buttons, extra) {
  const out = (extra || []).map(label => `<span class="d-btn d-btn-secondary">${esc(label)}</span>`);
  (buttons || []).forEach(b => {
    const bg = STYLE_BG[b.style] || STYLE_BG.primary;
    out.unshift(`<span class="d-btn" style="background:${bg};">${b.emoji ? esc(b.emoji) + " " : ""}${esc(b.label || "Action")}</span>`);
  });
  return out.join("");
}

// ============================================================
// Selecteur d'entites Home Assistant (modal)
// ============================================================
let _haEntities = null;
async function loadEntities() {
  if (_haEntities) return _haEntities;
  try { _haEntities = await API.get("/ha/entities"); } catch { _haEntities = []; }
  return _haEntities;
}

// Domaines connus : libelle FR + icone (les autres sont affiches tels quels).
const DOMAIN_META = {
  light:         ["Lumières", "💡"],
  switch:        ["Interrupteurs", "🔌"],
  sensor:        ["Capteurs", "📊"],
  binary_sensor: ["Capteurs bin.", "⚪"],
  climate:       ["Chauffage/clim", "🌡️"],
  cover:         ["Volets", "🪟"],
  lock:          ["Serrures", "🔒"],
  person:        ["Personnes", "🧍"],
  device_tracker:["Présence", "📍"],
  media_player:  ["Média", "🎵"],
  fan:           ["Ventilation", "🌀"],
  vacuum:        ["Aspirateurs", "🧹"],
  camera:        ["Caméras", "📷"],
  weather:       ["Météo", "⛅"],
  automation:    ["Automatisations", "⚙️"],
  scene:         ["Scènes", "🎬"],
  script:        ["Scripts", "📜"],
  input_boolean: ["Booléens", "🔘"],
  input_number:  ["Nombres", "🔢"],
  sun:           ["Soleil", "☀️"],
  button:        ["Boutons", "🔴"],
  input_button:  ["Boutons", "🔴"],
  number:        ["Nombres", "🔢"],
  update:        ["Mises à jour", "⬆️"],
  select:        ["Listes", "📋"],
  input_select:  ["Listes", "📋"],
  input_text:    ["Textes", "📝"],
  input_datetime:["Dates/heures", "📅"],
  timer:         ["Minuteries", "⏲️"],
};
const SMALL_MAX = 5;          // domaines avec < SMALL_MAX entites -> regroupes dans « Divers »
const DIVERS = "__divers__";  // cle synthetique du groupe fourre-tout
function domainLabel(d) { return d === DIVERS ? "Divers" : (DOMAIN_META[d] || [d, "📦"])[0]; }
function domainIcon(d)  { return d === DIVERS ? "🗃️" : (DOMAIN_META[d] || [d, "📦"])[1]; }
function entDomainOf(e) { return e.domain || (e.entity_id || "").split(".")[0]; }

let _entModal = null, _entOnPick = null, _entDomain = null;

function _entEls() {
  if (_entModal) return _entModal;
  const wrap = document.createElement("div");
  wrap.className = "ent-modal";
  wrap.innerHTML = `
    <div class="ent-modal-box">
      <div class="ent-modal-head">
        <strong>Choisir une entite Home Assistant</strong>
        <button type="button" class="btn btn-secondary btn-small" data-ent-close>Fermer</button>
      </div>
      <input type="text" class="form-input" data-ent-search placeholder="Filtrer par nom ou entity_id...">
      <div class="ent-domain-bar" data-ent-bar></div>
      <div class="ent-modal-list" data-ent-list></div>
      <div class="form-hint" data-ent-hint style="margin-top:0.5rem;"></div>
    </div>`;
  document.body.appendChild(wrap);
  _entModal = {
    root: wrap,
    search: wrap.querySelector("[data-ent-search]"),
    bar: wrap.querySelector("[data-ent-bar]"),
    list: wrap.querySelector("[data-ent-list]"),
    hint: wrap.querySelector("[data-ent-hint]"),
  };
  _entModal.search.addEventListener("input", () => _renderEntList(_entModal.search.value));
  _entModal.bar.addEventListener("click", (e) => {
    const chip = e.target.closest(".ent-chip");
    if (!chip) return;
    _entDomain = chip.dataset.domain || null;
    _renderDomainBar();
    _renderEntList(_entModal.search.value);
  });
  wrap.querySelector("[data-ent-close]").addEventListener("click", closeEntityPicker);
  wrap.addEventListener("click", (e) => { if (e.target === wrap) closeEntityPicker(); });
  _entModal.list.addEventListener("click", (e) => {
    const item = e.target.closest(".ent-item");
    if (!item || !_entOnPick) return;
    const cb = _entOnPick;
    closeEntityPicker();
    cb(item.dataset.eid);
  });
  return _entModal;
}

function _domainCounts() {
  const c = {};
  for (const e of (_haEntities || [])) {
    const d = entDomainOf(e);
    c[d] = (c[d] || 0) + 1;
  }
  return c;
}
function _bucketOf(e, counts) {
  const d = entDomainOf(e);
  return (counts[d] || 0) < SMALL_MAX ? DIVERS : d;
}

function _renderDomainBar() {
  const counts = _domainCounts();
  const bucket = {};
  for (const e of (_haEntities || [])) {
    const b = _bucketOf(e, counts);
    bucket[b] = (bucket[b] || 0) + 1;
  }
  const keys = Object.keys(bucket).filter(k => k !== DIVERS)
    .sort((a, b) => bucket[b] - bucket[a] || a.localeCompare(b));
  const total = (_haEntities || []).length;
  const chip = (val, label, icon, n, active) =>
    `<button type="button" class="ent-chip${active ? " active" : ""}" data-domain="${val === null ? "" : esc(val)}">`
    + `${icon} ${esc(label)}<span class="ent-chip-count">${n}</span></button>`;
  let html = chip(null, "Tous", "🗂️", total, _entDomain === null);
  html += keys.map(d =>
    chip(d, domainLabel(d), domainIcon(d), bucket[d], _entDomain === d)).join("");
  if (bucket[DIVERS])  // le fourre-tout en dernier
    html += chip(DIVERS, "Divers", domainIcon(DIVERS), bucket[DIVERS], _entDomain === DIVERS);
  _entEls().bar.innerHTML = html;
}

function _renderEntList(filter) {
  const q = (filter || "").toLowerCase();
  const counts = _domainCounts();
  const matches = (_haEntities || []).filter(e =>
    (_entDomain === null || _bucketOf(e, counts) === _entDomain) &&
    (!q || e.entity_id.toLowerCase().includes(q) ||
      (e.friendly_name || "").toLowerCase().includes(q)));

  // Regroupe par bucket (les petits domaines sont fondus dans « Divers »).
  const groups = {};
  for (const e of matches) {
    const b = _bucketOf(e, counts);
    (groups[b] = groups[b] || []).push(e);
  }
  const order = Object.keys(groups).filter(k => k !== DIVERS)
    .sort((a, b) => groups[b].length - groups[a].length || a.localeCompare(b));
  if (groups[DIVERS]) order.push(DIVERS);  // « Divers » toujours a la fin

  let shown = 0, html = "";
  for (const d of order) {
    if (shown >= 400) break;
    const items = groups[d];
    html += `<div class="ent-group-head">${domainIcon(d)} ${esc(domainLabel(d))}`
      + `<span class="ent-group-count"> · ${items.length}</span></div>`;
    for (const e of items) {
      if (shown >= 400) break;
      shown++;
      const val = e.state ? esc(e.state) + (e.unit ? " " + esc(e.unit) : "") : "";
      html += `<div class="ent-item" data-eid="${esc(e.entity_id)}">
        <div class="ent-item-row">
          <div class="ent-item-main">
            <strong>${esc(e.friendly_name || e.entity_id)}</strong>
            <code>${esc(e.entity_id)}</code>
          </div>
          ${val ? `<div class="ent-state" title="${val}">${val}</div>` : ""}
        </div>
      </div>`;
    }
  }
  _entEls().list.innerHTML = html || `<div class="empty-state">Aucune entité</div>`;
}

async function openEntityPicker(onPick, hint) {
  const els = _entEls();
  _entOnPick = onPick;
  els.hint.textContent = hint || "Clique sur une entite pour l'inserer.";
  els.search.value = "";
  _entDomain = null;
  els.root.classList.add("open");
  await loadEntities();
  _renderDomainBar();
  _renderEntList("");
  setTimeout(() => els.search.focus(), 50);
}

function closeEntityPicker() {
  if (_entModal) _entModal.root.classList.remove("open");
  _entOnPick = null;
}

// Ouvre le selecteur et insere {state:<entite>|--} a la position du curseur.
function pickEntityInto(inputEl) {
  openEntityPicker((eid) => insertAtCursor(inputEl, `{state:${eid}|--}`),
    "L'entite sera inseree comme {state:...|--} (sa valeur en direct).");
}

// ============================================================
// Presets de couleurs : pastilles cliquables + « enregistrer comme preset »
// ============================================================
async function bindColorPresets(colorInput, container) {
  let presets = [];
  try { presets = await API.get("/settings/colors"); } catch { presets = []; }

  function render() {
    const cur = (colorInput.value || "").toLowerCase();
    container.innerHTML = presets.map((p, i) => {
      const hex = colorToHex(p.color);
      return `<button type="button" class="swatch${hex === cur ? " active" : ""}" data-i="${i}"
                title="${esc(p.name)} (${hex})" style="background:${hex};"></button>`;
    }).join("") +
      `<button type="button" class="swatch swatch-add" data-add title="Enregistrer la couleur actuelle comme preset">＋</button>`;
  }

  container.addEventListener("click", async (e) => {
    const sw = e.target.closest(".swatch");
    if (!sw) return;
    if (sw.dataset.add !== undefined) {
      const name = (prompt("Nom du nouveau preset de couleur (ex : Alerte porte) :") || "").trim();
      if (!name) return;
      try {
        presets = await API.post("/settings/colors", { name: name.slice(0, 64), color: hexToInt(colorInput.value) });
        toast(`Preset « ${name} » enregistré`);
        render();
      } catch (err) { toast(err.message, "error"); }
      return;
    }
    const p = presets[+sw.dataset.i];
    if (!p) return;
    colorInput.value = colorToHex(p.color);
    colorInput.dispatchEvent(new Event("input", { bubbles: true }));
  });
  colorInput.addEventListener("input", render);
  colorInput.addEventListener("change", render);
  render();
}

// ============================================================
// Channels Discord : favoris (Parametres) + channels detectes par le bot
// ============================================================
async function bindChannelSelect(sel, idInput, emptyLabel) {
  const [presets, botCh] = await Promise.all([
    API.get("/settings/channels").catch(() => []),
    API.get("/discord/channels").catch(() => []),
  ]);
  const opts = [`<option value="">${esc(emptyLabel || "— choisir —")}</option>`];
  if (presets.length) {
    opts.push('<optgroup label="★ Favoris">');
    presets.forEach(p => opts.push(
      `<option value="${esc(p.channel_id)}">★ ${esc(p.name)}</option>`
    ));
    opts.push('</optgroup>');
  }
  if (botCh.length) {
    opts.push('<optgroup label="Détectés par le bot">');
    botCh.forEach(c => opts.push(
      `<option value="${esc(c.id)}"># ${esc(c.name)}${c.category ? " — " + esc(c.category) : ""}</option>`
    ));
    opts.push('</optgroup>');
  }
  sel.innerHTML = opts.join("");
  sel.addEventListener("change", () => {
    if (sel.value) idInput.value = sel.value;
    idInput.dispatchEvent(new Event("input", { bubbles: true }));
  });
  idInput.addEventListener("input", () => {
    const v = idInput.value.trim();
    sel.value = [...sel.options].some(o => o.value === v) ? v : "";
  });
  if (idInput.value) sel.value = idInput.value;
}

// ============================================================
// Constructeur de boutons d'action Home Assistant
//   list     : tableau d'objets {label, style, emoji, ha_service, ha_entity_id, ha_data_json}
//              (modifie sur place : les champs inconnus, ex. id, sont conserves)
//   onChange : rappel apres chaque modif (apercu)
// ============================================================
function createHaButtonsBuilder(container, getList, onChange) {
  const changed = () => { if (onChange) onChange(); };

  function render() {
    const list = getList();
    container.innerHTML = list.map((b, i) => `
      <div class="ha-btn-row" data-bidx="${i}">
        <div class="ha-btn-grid">
          <div>
            <label class="form-label">Texte du bouton</label>
            <div style="display:flex; gap:0.3rem;">
              <input class="form-input" data-bk="emoji" value="${esc(b.emoji || "")}" placeholder="😀" style="width:3.2rem; text-align:center;">
              <input class="form-input" data-bk="label" value="${esc(b.label || "")}" placeholder="Allumer" style="flex:1;">
              <button type="button" class="md-btn" data-bemoji title="Choisir un emoji">😀</button>
            </div>
          </div>
          <div>
            <label class="form-label">Couleur</label>
            <select class="form-select" data-bk="style">
              ${Object.keys(STYLE_BG).map(s =>
                `<option value="${s}" ${s === (b.style || "primary") ? "selected" : ""}>${STYLE_LABEL[s]}</option>`).join("")}
            </select>
          </div>
          <div>
            <label class="form-label">Action HA (service)</label>
            <input class="form-input ha-service-input" data-bk="ha_service" value="${esc(b.ha_service || "")}" placeholder="light.toggle">
          </div>
          <div>
            <label class="form-label">Entité</label>
            <div style="display:flex; gap:0.3rem;">
              <input class="form-input ha-entity-input" data-bk="ha_entity_id" value="${esc(b.ha_entity_id || "")}" placeholder="light.salon" style="flex:1;">
              <button type="button" class="md-btn" data-bpick title="Choisir une entité">🔍</button>
            </div>
          </div>
        </div>
        <details class="ha-btn-adv" ${b.ha_data_json ? "open" : ""}>
          <summary>Options avancées (data JSON)</summary>
          <input class="form-input" data-bk="ha_data_json" value="${esc(b.ha_data_json || "")}" placeholder='{"brightness": 255}'>
        </details>
        <div class="ha-btn-tools">
          <button type="button" class="md-btn" data-bup ${i === 0 ? "disabled" : ""} title="Monter">↑</button>
          <button type="button" class="md-btn" data-bdown ${i === list.length - 1 ? "disabled" : ""} title="Descendre">↓</button>
          <button type="button" class="btn btn-danger btn-small" data-bdel>Retirer</button>
        </div>
      </div>
    `).join("") || `<div class="hint" style="margin:0;">Aucun bouton pour l'instant.</div>`;

    container.querySelectorAll(".ha-btn-row").forEach(row => {
      const idx = +row.dataset.bidx;
      const item = () => getList()[idx];
      row.querySelectorAll("[data-bk]").forEach(inp => {
        const sync = () => { item()[inp.dataset.bk] = inp.value; changed(); };
        inp.addEventListener("input", sync);
        inp.addEventListener("change", sync);
      });
      row.querySelector("[data-bemoji]").addEventListener("click", () =>
        openEmojiPicker((e) => {
          const inp = row.querySelector('[data-bk="emoji"]');
          inp.value = e;
          inp.dispatchEvent(new Event("input", { bubbles: true }));
        }));
      row.querySelector("[data-bpick]").addEventListener("click", () =>
        openEntityPicker((eid) => {
          const inp = row.querySelector('[data-bk="ha_entity_id"]');
          inp.value = eid;
          inp.dispatchEvent(new Event("input", { bubbles: true }));
        }, "Entité ciblée par le bouton."));
      const move = (delta) => {
        const list = getList();
        const [it] = list.splice(idx, 1);
        list.splice(idx + delta, 0, it);
        render(); changed();
      };
      row.querySelector("[data-bup]").addEventListener("click", () => move(-1));
      row.querySelector("[data-bdown]").addEventListener("click", () => move(1));
      row.querySelector("[data-bdel]").addEventListener("click", () => {
        getList().splice(idx, 1);
        render(); changed();
      });
      attachAutocomplete(row.querySelector(".ha-service-input"), "/ha/services",
        it => it.service, it => it.service);
      attachAutocomplete(row.querySelector(".ha-entity-input"), "/ha/entities",
        it => it.friendly_name, it => it.entity_id);
    });
  }

  return {
    render,
    add() {
      getList().push({ label: "Action", style: "primary", emoji: "", ha_service: "", ha_entity_id: "", ha_data_json: "" });
      render(); changed();
    },
  };
}

// Nettoie la liste de boutons avant envoi a l'API (champs vides -> null).
function cleanHaButtons(list) {
  return (list || [])
    .filter(b => (b.label || "").trim() && (b.ha_service || "").trim())
    .map(b => ({
      label: b.label.trim(),
      style: b.style || "primary",
      emoji: (b.emoji || "").trim() || null,
      ha_service: b.ha_service.trim(),
      ha_entity_id: (b.ha_entity_id || "").trim() || null,
      ha_data_json: (b.ha_data_json || "").trim() || null,
    }));
}

// ============================================================
// Pages liste : regroupement repliable (meme rendu que les notifications)
// ============================================================
function renderGroupedList(root, items, groupOf, rowHtml, storageKey) {
  const byGroup = new Map();
  for (const it of items) {
    const key = (groupOf(it) || "").trim();
    if (!byGroup.has(key)) byGroup.set(key, []);
    byGroup.get(key).push(it);
  }
  const names = [...byGroup.keys()].sort((a, b) => {
    if (a === "" && b !== "") return 1;
    if (b === "" && a !== "") return -1;
    return a.localeCompare(b);
  });

  let closed;
  try { closed = new Set(JSON.parse(localStorage.getItem(storageKey) || "[]")); }
  catch { closed = new Set(); }

  root.innerHTML = names.map(name => {
    const list = byGroup.get(name);
    return `
      <details class="card group-card" data-group="${esc(name)}" ${closed.has(name) ? "" : "open"}>
        <summary>
          <span class="group-arrow">&#9656;</span>
          <span class="group-name">${esc(name || "Sans groupe")}</span>
          <span class="group-count">${list.length}</span>
        </summary>
        <div class="group-list">${list.map(rowHtml).join("")}</div>
      </details>`;
  }).join("");

  root.querySelectorAll("details.group-card").forEach(d => {
    d.addEventListener("toggle", () => {
      let set;
      try { set = new Set(JSON.parse(localStorage.getItem(storageKey) || "[]")); }
      catch { set = new Set(); }
      if (d.open) set.delete(d.dataset.group); else set.add(d.dataset.group);
      try { localStorage.setItem(storageKey, JSON.stringify([...set])); } catch { /* ignore */ }
    });
  });
}

// Remplit un <datalist> avec des valeurs uniques triees.
function fillDatalist(dl, values) {
  if (!dl) return;
  dl.innerHTML = [...new Set(values.filter(Boolean))].sort()
    .map(v => `<option value="${esc(v)}">`).join("");
}
