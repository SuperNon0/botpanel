/* BotPanel — squelettes de chargement.
   Remplit tout conteneur `data-skeleton="N"` avec N lignes « skeleton » dès le
   chargement (synchrone). Le script propre de la page remplace ensuite le
   contenu quand les données arrivent. Si rien ne remplace (JS de page en échec),
   le squelette reste — jamais une page blanche. */
(function () {
  try {
    var nodes = document.querySelectorAll("[data-skeleton]");
    for (var k = 0; k < nodes.length; k++) {
      var el = nodes[k];
      if (el.children.length) continue; // ne pas écraser un contenu déjà présent
      var n = parseInt(el.getAttribute("data-skeleton"), 10) || 3;
      var html = '<div class="skel-list" aria-hidden="true">';
      for (var i = 0; i < n; i++) {
        html += '<div class="skel-row">'
          + '<div class="skel-main">'
          + '<span class="skeleton skel-line" style="width:' + (32 + (i % 3) * 8) + '%"></span>'
          + '<span class="skeleton skel-line skel-sub" style="width:' + (58 + (i % 2) * 10) + '%"></span>'
          + '</div><span class="skeleton skel-pill"></span></div>';
      }
      html += "</div>";
      el.innerHTML = html;
    }
  } catch (e) { /* ne jamais bloquer le rendu */ }
})();

/* BotPanel — animations d'entrée (progressive enhancement).
   Pose la classe .bp-in (fondu + glissement) sur les blocs principaux, en
   décalé. Ne cache jamais rien : les keyframes finissent à opacity:1, et si
   JS ne tourne pas, la page s'affiche normalement. Désactivé si l'utilisateur
   préfère réduire les animations. */
(function () {
  try {
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;

    function reveal() {
      var sel = "main > .page-header, main .card, main .fl-card, main > section";
      var els = document.querySelectorAll(sel);
      var i = 0;
      els.forEach(function (el) {
        if (el.dataset.bpIn) return;      // évite le double passage
        el.dataset.bpIn = "1";
        el.style.animationDelay = Math.min(i * 55, 380) + "ms";
        el.classList.add("bp-in");
        i++;
      });
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", reveal);
    } else {
      reveal();
    }
  } catch (e) { /* jamais bloquer le rendu pour une animation */ }
})();
