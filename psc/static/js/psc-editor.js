/* Éditeur de texte riche.
   Le serveur rend un textarea ordinaire. Ce script le remplace par l'éditeur
   quand il est disponible ; sans lui, la saisie reste possible en texte brut,
   et le serveur assainit dans les deux cas. */

(function () {
  "use strict";

  var TOOLBAR = [
    ["bold", "italic", "underline"],
    [{ list: "bullet" }, { list: "ordered" }],
    ["link"],
    ["clean"],
  ];

  var LABELS = {
    "ql-bold": "Gras",
    "ql-italic": "Italique",
    "ql-underline": "Souligné",
    "ql-list": "Liste",
    "ql-link": "Lien",
    "ql-clean": "Retirer la mise en forme",
  };

  function enhance(textarea) {
    if (typeof Quill === "undefined" || textarea.dataset.richReady === "1") return;
    textarea.dataset.richReady = "1";

    var host = document.createElement("div");
    host.className = "psc-editor";
    var surface = document.createElement("div");
    surface.className = "psc-editor-surface";
    host.appendChild(surface);
    textarea.parentNode.insertBefore(host, textarea);
    textarea.classList.add("d-none");
    textarea.setAttribute("aria-hidden", "true");
    textarea.setAttribute("tabindex", "-1");

    var quill = new Quill(surface, {
      theme: "snow",
      placeholder: textarea.getAttribute("placeholder") || "",
      modules: { toolbar: TOOLBAR },
    });

    if (textarea.value.trim()) {
      quill.clipboard.dangerouslyPasteHTML(textarea.value);
    }

    // Les boutons de la barre d'outils n'ont pas de nom accessible par défaut.
    host.querySelectorAll(".ql-toolbar button").forEach(function (button) {
      var key = Array.prototype.find.call(button.classList, function (c) {
        return LABELS[c];
      });
      if (key) {
        button.setAttribute("title", LABELS[key]);
        button.setAttribute("aria-label", LABELS[key]);
      }
      button.setAttribute("type", "button");
    });

    var label = document.querySelector('label[for="' + textarea.id + '"]');
    if (label) {
      surface.querySelector(".ql-editor").setAttribute("aria-label", label.textContent.trim());
    }

    sync(textarea, quill);
  }

  function sync(textarea, quill) {
    function write() {
      // getSemanticHTML rend des <ul>/<ol> propres plutôt que les <li
      // data-list> internes de l'éditeur.
      var html = quill.getSemanticHTML().trim();
      textarea.value = quill.getText().trim() ? html : "";
    }
    quill.on("text-change", write);
    var form = textarea.closest("form");
    if (form) {
      form.addEventListener("submit", write);
      // HTMX sérialise le formulaire avant l'évènement submit natif.
      form.addEventListener("htmx:configRequest", write);
    }
    write();
  }

  function scan(root) {
    (root || document).querySelectorAll("textarea[data-rich]").forEach(enhance);
  }

  document.addEventListener("DOMContentLoaded", function () {
    scan(document);
  });
  document.body.addEventListener("htmx:afterSwap", function (event) {
    scan(event.target);
  });
  document.body.addEventListener("shown.bs.modal", function (event) {
    scan(event.target);
  });
})();
