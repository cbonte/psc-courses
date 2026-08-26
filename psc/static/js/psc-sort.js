/* Réordonner une liste en la faisant glisser.

   Sur pointeur, pas sur l'API HTML5 de glisser-déposer : celle-ci ignore le
   tactile, et ces écrans se consultent au téléphone. Les boutons monter et
   descendre restent le chemin sans JavaScript et au clavier ; ce fichier
   n'est qu'un raccourci. */

(function () {
  "use strict";

  var SEUIL = 4; // pixels avant de considérer que l'on glisse vraiment

  function rows(list) {
    return Array.prototype.slice.call(list.querySelectorAll("[data-pk]"));
  }

  function start(event) {
    var grip = event.target.closest("[data-grip]");
    if (!grip || event.button > 0) return;
    var row = grip.closest("[data-pk]");
    var list = grip.closest("[data-sortable]");
    if (!row || !list) return;

    event.preventDefault();
    var startY = event.clientY;
    var moved = false;

    function onMove(move) {
      if (!moved && Math.abs(move.clientY - startY) < SEUIL) return;
      if (!moved) {
        moved = true;
        row.classList.add("is-dragging");
        list.classList.add("is-sorting");
        grip.setPointerCapture(move.pointerId);
      }
      // On insère la ligne selon la position du pointeur par rapport au
      // milieu de chaque voisine : pas de fantôme à gérer, le DOM suit.
      var others = rows(list).filter(function (other) {
        return other !== row;
      });
      var before = others.find(function (other) {
        var box = other.getBoundingClientRect();
        return move.clientY < box.top + box.height / 2;
      });
      if (before) {
        if (before.previousElementSibling !== row) list.insertBefore(row, before);
      } else if (list.lastElementChild !== row) {
        list.appendChild(row);
      }
    }

    function onUp() {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
      row.classList.remove("is-dragging");
      list.classList.remove("is-sorting");
      if (moved) save(list);
    }

    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
    document.addEventListener("pointercancel", onUp);
  }

  function save(list) {
    if (!window.htmx) return;
    var order = rows(list).map(function (row) {
      return row.getAttribute("data-pk");
    });
    window.htmx.ajax("POST", list.getAttribute("data-order-url"), {
      target: list,
      swap: "outerHTML",
      values: { order: order },
    });
  }

  document.addEventListener("pointerdown", start);
})();
