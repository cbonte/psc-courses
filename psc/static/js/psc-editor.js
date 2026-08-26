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

  /* L'éditeur pèse une soixantaine de kilo-octets et ne sert que sur trois
     pages sur neuf. On ne le charge qu'au moment où un champ riche apparaît,
     y compris quand il arrive par HTMX. */

  var loading = false;
  var waiting = [];

  function withQuill(run) {
    if (window.Quill) return run();
    waiting.push(run);
    if (loading) return;
    loading = true;

    var body = document.body;
    var css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = body.getAttribute("data-quill-css");
    document.head.appendChild(css);

    var js = document.createElement("script");
    js.src = body.getAttribute("data-quill-js");
    js.onload = function () {
      loading = false;
      waiting.splice(0).forEach(function (fn) {
        fn();
      });
    };
    js.onerror = function () {
      loading = false;
      waiting.length = 0;
      // Sans éditeur, le textarea d'origine reste utilisable tel quel.
    };
    document.head.appendChild(js);
  }

  function enhance(textarea) {
    if (textarea.dataset.richReady === "1") return;
    textarea.dataset.richReady = "1";
    withQuill(function () {
      build(textarea);
    });
  }

  function build(textarea) {

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
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("textarea[data-rich]").forEach(enhance);
    if (root.matches && root.matches("textarea[data-rich]")) enhance(root);
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
