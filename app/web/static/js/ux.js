// Confort d'utilisation (thème Atelier) :
//  - confirmBox()      : fenêtre de confirmation au style du site
//  - menu « ⋯ »        : .row-menu > .row-menu-btn + .row-menu-list
//  - recherche         : <div class="list-search"><input data-search="#groups-root"></div>
//  - Ctrl/Cmd+S        : enregistre le formulaire d'édition de la page
//  - modifs non enregistrées : <form data-dirty-guard>, prévient avant de quitter
//    (appeler markSaved() après un enregistrement réussi).

// ---------- Confirmation ----------
// Remplace confirm() : renvoie une Promise<boolean>.
// opts : { title, ok, cancel, danger }
function confirmBox(message, opts = {}) {
  const danger = opts.danger ?? /supprim|régénér|regener|désactiv|remplac|réinitialis|reinitialis/i.test(message);
  return new Promise(resolve => {
    const prevFocus = document.activeElement;
    const ov = document.createElement("div");
    ov.className = "confirm-overlay";
    ov.innerHTML = `
      <div class="confirm-box" role="alertdialog" aria-modal="true" aria-labelledby="cf-title" aria-describedby="cf-msg">
        <h3 id="cf-title">${esc(opts.title || (danger ? "Tu confirmes ?" : "Confirmer"))}</h3>
        <p id="cf-msg">${esc(message)}</p>
        <div class="confirm-actions">
          <button type="button" class="btn btn-secondary" data-r="0">${esc(opts.cancel || "Annuler")}</button>
          <button type="button" class="btn ${danger ? "btn-danger" : "btn-primary"}" data-r="1">${esc(opts.ok || (danger ? "Oui, continuer" : "OK"))}</button>
        </div>
      </div>`;
    const close = (val) => {
      document.removeEventListener("keydown", onKey, true);
      ov.remove();
      if (prevFocus && prevFocus.focus) prevFocus.focus();
      resolve(val);
    };
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); close(false); }
      if (e.key === "Tab") {
        // garde le focus dans la fenêtre
        const btns = [...ov.querySelectorAll("button")];
        const i = btns.indexOf(document.activeElement);
        e.preventDefault();
        btns[(i + (e.shiftKey ? -1 : 1) + btns.length) % btns.length].focus();
      }
    };
    ov.addEventListener("click", (e) => {
      if (e.target === ov) return close(false);
      const b = e.target.closest("[data-r]");
      if (b) close(b.dataset.r === "1");
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(ov);
    ov.querySelector(danger ? '[data-r="0"]' : '[data-r="1"]').focus();
  });
}

// ---------- Menu « ⋯ » ----------
function closeRowMenus(except) {
  document.querySelectorAll(".row-menu.open").forEach(m => {
    if (m === except) return;
    m.classList.remove("open");
    const b = m.querySelector(".row-menu-btn");
    if (b) b.setAttribute("aria-expanded", "false");
  });
}
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".row-menu-btn");
  if (btn) {
    const menu = btn.closest(".row-menu");
    const open = !menu.classList.contains("open");
    closeRowMenus(menu);
    menu.classList.toggle("open", open);
    btn.setAttribute("aria-expanded", String(open));
    if (open) { const first = menu.querySelector(".row-menu-list button"); if (first) first.focus(); }
    return;
  }
  // un clic sur une action du menu ou ailleurs referme les menus
  closeRowMenus(null);
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeRowMenus(null); });

// HTML du menu « ⋯ » d'une ligne (Cloner + Supprimer)
function rowMenuHtml(id) {
  return `<div class="row-menu">
    <button type="button" class="btn btn-secondary btn-small row-menu-btn" aria-haspopup="true" aria-expanded="false" title="Plus d'actions" aria-label="Plus d'actions">⋯</button>
    <div class="row-menu-list" role="menu">
      <button type="button" role="menuitem" data-dup="${id}">Cloner</button>
      <button type="button" role="menuitem" class="danger" data-del="${id}">Supprimer</button>
    </div>
  </div>`;
}

// ---------- Recherche dans les listes ----------
function norm(s) {
  return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}
function applyListSearch(input) {
  const root = document.querySelector(input.dataset.search);
  if (!root) return;
  const q = norm(input.value.trim());
  let shown = 0;
  root.querySelectorAll(".group-card").forEach(g => {
    let n = 0;
    g.querySelectorAll(".card-row").forEach(r => {
      const ok = !q || norm(r.textContent).includes(q);
      r.classList.toggle("row-hidden", !ok);
      if (ok) n++;
    });
    g.classList.toggle("group-hidden", n === 0);
    if (q && n) g.open = true;
    shown += n;
  });
  let empty = root.parentNode.querySelector(".search-empty");
  if (q && shown === 0) {
    if (!empty) {
      empty = document.createElement("div");
      empty.className = "search-empty";
      root.after(empty);
    }
    empty.textContent = `Rien ne correspond à « ${input.value.trim()} ».`;
  } else if (empty) {
    empty.remove();
  }
}
document.querySelectorAll("input[data-search]").forEach(input => {
  input.addEventListener("input", () => applyListSearch(input));
  // la liste se recharge (activation, suppression…) : on réapplique le filtre
  const root = document.querySelector(input.dataset.search);
  if (root) new MutationObserver(() => { if (input.value) applyListSearch(input); })
    .observe(root, { childList: true });
});
// « / » place le curseur dans la recherche (hors champ de saisie)
document.addEventListener("keydown", (e) => {
  if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest("input, textarea, select, [contenteditable]")) return;
  const s = document.querySelector("input[data-search]");
  if (s) { e.preventDefault(); s.focus(); }
});

// ---------- Ctrl/Cmd+S + modifications non enregistrées ----------
const editForm = document.querySelector("main form[data-dirty-guard]");
let formDirty = false;
function markSaved() {
  formDirty = false;
  if (editForm) editForm.classList.remove("is-dirty");
}
if (editForm) {
  // Les champs sont remplis par script au chargement : on ne compte les
  // changements qu'après une vraie action de l'utilisateur dans le formulaire.
  let touched = false;
  const touch = (e) => { if (e.isTrusted) touched = true; };
  editForm.addEventListener("pointerdown", touch, true);
  editForm.addEventListener("keydown", touch, true);
  const onChange = () => {
    if (!touched) return;
    formDirty = true;
    editForm.classList.add("is-dirty");
  };
  editForm.addEventListener("input", onChange);
  editForm.addEventListener("change", onChange);
  window.addEventListener("beforeunload", (e) => {
    if (!formDirty) return;
    e.preventDefault();
    e.returnValue = "";
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (document.querySelector(".confirm-overlay, .help-overlay.open, .ent-modal.open")) return;
      editForm.requestSubmit();
    }
  });
}
