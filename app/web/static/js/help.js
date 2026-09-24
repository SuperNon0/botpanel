/* BotPanel — aide contextuelle : petits « ? » qui ouvrent une pop-up.

   Usage dans un template :
     <button type="button" class="help-dot" data-help="slug">?</button>
   Le contenu est défini dans help-content.js (objet global BP_HELP).

   La pop-up supporte du HTML riche (couleurs, blocs de code avec bouton Copier).
   Aucune dépendance ; se dégrade sans bruit si une clé est absente. */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "help-overlay";
    overlay.innerHTML =
      '<div class="help-modal" role="dialog" aria-modal="true">' +
      '  <button type="button" class="help-close" aria-label="Fermer">&times;</button>' +
      '  <h3 class="help-title"></h3>' +
      '  <div class="help-body"></div>' +
      "</div>";
    document.body.appendChild(overlay);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeHelp();
    });
    overlay.querySelector(".help-close").addEventListener("click", closeHelp);
    overlay.addEventListener("click", function (e) {
      var btn = e.target.closest(".copy-btn");
      if (!btn) return;
      var holder = btn.closest(".code-block") || btn.parentNode;
      var pre = holder ? holder.querySelector("pre, code") : null;
      var text = btn.getAttribute("data-copy") || (pre ? pre.textContent : "");
      copyText(text, btn);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeHelp();
    });
    return overlay;
  }

  function copyText(text, btn) {
    var old = btn.textContent;
    var done = function () {
      btn.textContent = "Copié ✓";
      btn.classList.add("copied");
      setTimeout(function () { btn.textContent = old; btn.classList.remove("copied"); }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text, done); });
    } else {
      fallbackCopy(text, done);
    }
  }
  function fallbackCopy(text, done) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); document.body.removeChild(ta); done();
    } catch (e) { /* ignore */ }
  }

  function openHelp(key) {
    var entry = (window.BP_HELP || {})[key];
    if (!entry) entry = { title: "Aide", html: "<p>Aucune explication disponible.</p>" };
    var ov = ensureOverlay();
    ov.querySelector(".help-title").innerHTML = esc(entry.title || "Aide");
    ov.querySelector(".help-body").innerHTML = entry.html || "";
    ov.classList.add("open");
    document.body.classList.add("help-lock");
  }

  function closeHelp() {
    if (!overlay) return;
    overlay.classList.remove("open");
    document.body.classList.remove("help-lock");
  }

  document.addEventListener("click", function (e) {
    var dot = e.target.closest(".help-dot");
    if (!dot) return;
    e.preventDefault();
    openHelp(dot.getAttribute("data-help"));
  });

  function showHtml(title, html) {
    var ov = ensureOverlay();
    ov.querySelector(".help-title").innerHTML = esc(title || "Aide");
    ov.querySelector(".help-body").innerHTML = html || "";
    ov.classList.add("open");
    document.body.classList.add("help-lock");
  }

  // open(key) : contenu depuis BP_HELP. show(title, html) : contenu ad hoc.
  window.BPHelp = { open: openHelp, close: closeHelp, show: showHtml };
})();
