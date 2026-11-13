/* BotPanel — aide contextuelle : petits « ? » qui ouvrent une feuille d'aide.

   Usage dans un template :
     <button type="button" class="help-dot" data-help="slug">?</button>
   Le contenu est défini dans help-content.js (objet global BP_HELP).

   La feuille vient du design « encre » (Encre.feuille) : elle monte du bas sur
   téléphone, s'ouvre au centre sur ordinateur, et le bouton retour du
   téléphone la referme. Elle accepte du HTML riche (encadrés, blocs de code
   avec bouton Copier). Se dégrade sans bruit si une clé est absente. */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var ouverte = null;

  function showHtml(title, html) {
    if (!window.Encre) return;
    if (ouverte && !ouverte.ferme) ouverte.fermer();
    ouverte = Encre.feuille({
      titre: esc(title || "Aide"),
      html: '<div class="help-body">' + (html || "") + "</div>",
      classe: "bp-aide",
    });
  }

  function openHelp(key) {
    var entry = (window.BP_HELP || {})[key];
    if (!entry) entry = { title: "Aide", html: "<p>Aucune explication disponible.</p>" };
    showHtml(entry.title || "Aide", entry.html || "");
  }

  function closeHelp() {
    if (ouverte && !ouverte.ferme) ouverte.fermer();
  }

  function copyText(text, btn) {
    var old = btn.textContent;
    var done = function () {
      btn.textContent = "Copié";
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

  document.addEventListener("click", function (e) {
    var dot = e.target.closest(".help-dot");
    if (dot) {
      e.preventDefault();
      openHelp(dot.getAttribute("data-help"));
      return;
    }
    // Bouton « Copier » d'un bloc de code dans une feuille d'aide.
    var btn = e.target.closest(".bp-aide .copy-btn");
    if (!btn) return;
    var holder = btn.closest(".code-block") || btn.parentNode;
    var pre = holder ? holder.querySelector("pre, code") : null;
    copyText(btn.getAttribute("data-copy") || (pre ? pre.textContent : ""), btn);
  });

  // open(key) : contenu depuis BP_HELP. show(title, html) : contenu ad hoc.
  window.BPHelp = { open: openHelp, close: closeHelp, show: showHtml };
})();
