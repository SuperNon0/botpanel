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
