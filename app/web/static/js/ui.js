// Helpers UI : toast, autocomplete

function toast(message, kind = "ok") {
  // Messages du design « encre » (posés au-dessus de la barre flottante).
  const go = () => window.Encre && Encre.toast(String(message ?? ""), { erreur: kind === "error" });
  if (window.Encre) go(); else document.addEventListener("DOMContentLoaded", go, { once: true });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// Icônes (SVG inline) pour les états vides
const _ic = (nom) => `<svg class="i" aria-hidden="true"><use href="/static/encre/icones.svg#i-${nom}"/></svg>`;
const ICONS = {
  bell: _ic("bell"),
  slash: _ic("hash"),
  pulse: _ic("signal"),
  clock: _ic("clock")
};

// Construit un état vide illustré (icône + titre + sous-texte + éventuel CTA)
function emptyBox(icon, title, sub, cta) {
  return `<div class="empty-state">
    <div class="empty-ico">${icon || ICONS.bell}</div>
    <div class="empty-title">${esc(title)}</div>
    ${sub ? `<div class="empty-sub">${sub}</div>` : ""}
    ${cta ? `<div class="empty-cta">${cta}</div>` : ""}
  </div>`;
}

// Champ input avec autocompletion depuis un endpoint /api/ha/*
// Params : inputEl, fetchUrl, formatLabel(item) -> string, getValue(item) -> string
async function attachAutocomplete(inputEl, fetchUrl, formatLabel, getValue) {
  const wrapper = document.createElement("div");
  wrapper.className = "autocomplete";
  inputEl.parentNode.insertBefore(wrapper, inputEl);
  wrapper.appendChild(inputEl);

  const results = document.createElement("div");
  results.className = "autocomplete-results";
  wrapper.appendChild(results);

  let items = [];
  try {
    items = await API.get(fetchUrl);
  } catch (e) {
    console.warn("Autocomplete HA indisponible :", e);
    return;
  }

  function render(filter) {
    const q = filter.toLowerCase();
    const matches = items
      .filter(i => !q || formatLabel(i).toLowerCase().includes(q) || getValue(i).toLowerCase().includes(q))
      .slice(0, 40);
    results.innerHTML = matches.map(i =>
      `<div class="autocomplete-item" data-value="${esc(getValue(i))}">
         ${esc(formatLabel(i))}<span class="eid">${esc(getValue(i))}</span>
       </div>`
    ).join("");
    results.classList.toggle("open", matches.length > 0);
  }

  inputEl.addEventListener("focus", () => render(inputEl.value));
  inputEl.addEventListener("input", () => render(inputEl.value));
  inputEl.addEventListener("blur", () => {
    setTimeout(() => results.classList.remove("open"), 150);
  });
  results.addEventListener("mousedown", (e) => {
    const item = e.target.closest(".autocomplete-item");
    if (!item) return;
    inputEl.value = item.dataset.value;
    results.classList.remove("open");
    inputEl.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
