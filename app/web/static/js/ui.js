// Helpers UI : toast, autocomplete

function toast(message, kind = "ok") {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.className = "toast show" + (kind === "error" ? " error" : "");
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    el.className = "toast" + (kind === "error" ? " error" : "");
  }, 2500);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// Icônes (SVG inline) pour les états vides
const ICONS = {
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>',
  slash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
  pulse: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3 8 4-16 3 8h4"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>'
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
