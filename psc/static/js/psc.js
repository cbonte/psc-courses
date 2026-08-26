/* Comportements propres au calendrier PSC.
   Tout le rendu vient du serveur ; ce fichier ne gère que ce qui doit
   survivre côté navigateur : le thème, l'identité mémorisée, les notifications. */

(function () {
  "use strict";

  var STORE_THEME = "psc-theme";
  var STORE_MEMBER = "psc-member-id";
  var SESSION_TRIED = "psc-restore-tried";

  function read(store, key) {
    try { return store.getItem(key); } catch (e) { return null; }
  }
  function write(store, key, value) {
    try { store.setItem(key, value); } catch (e) { /* navigation privée */ }
  }
  function drop(store, key) {
    try { store.removeItem(key); } catch (e) { /* ignore */ }
  }

  /* ----- thème clair / sombre ----- */

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-psc-theme-toggle]");
    if (!toggle) return;
    var root = document.documentElement;
    var next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-bs-theme", next);
    write(localStorage, STORE_THEME, next);
  });

  /* ----- identité mémorisée ----- */

  var body = document.body;
  var memberId = body.getAttribute("data-member-id");

  if (memberId) {
    // La session fait foi : on aligne la mémoire du navigateur dessus.
    write(localStorage, STORE_MEMBER, memberId);
    drop(sessionStorage, SESSION_TRIED);
  } else {
    var remembered = read(localStorage, STORE_MEMBER);
    // Une seule tentative par onglet, pour ne jamais boucler sur un rechargement.
    if (remembered && !read(sessionStorage, SESSION_TRIED)) {
      write(sessionStorage, SESSION_TRIED, "1");
      restoreIdentity(remembered);
    }
  }

  function restoreIdentity(id) {
    var url = body.getAttribute("data-restore-url");
    var token = getCookie("csrftoken");
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": token || "",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: "member=" + encodeURIComponent(id),
      credentials: "same-origin"
    })
      .then(function (response) {
        if (response.ok) {
          window.location.reload();
        } else {
          // Membre supprimé ou désactivé : on oublie.
          drop(localStorage, STORE_MEMBER);
        }
      })
      .catch(function () { /* hors ligne : on réessaiera plus tard */ });
  }

  document.body.addEventListener("psc:member-set", function (event) {
    if (event.detail && event.detail.id) {
      write(localStorage, STORE_MEMBER, String(event.detail.id));
    }
  });

  // Le serveur refuse une inscription sans identité : on ouvre la modale.
  document.body.addEventListener("psc:identity-needed", function () {
    var trigger = document.querySelector('[hx-get$="/moi/"]');
    var modalEl = document.getElementById("identity-modal");
    if (!modalEl || !window.bootstrap) return;
    var target = document.getElementById("identity-modal-body");
    if (target && window.htmx) {
      window.htmx.ajax("GET", "/moi/", { target: target, swap: "innerHTML" });
    }
    window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    if (trigger) { /* rien de plus : la modale porte le formulaire */ }
    notify("Indiquez d'abord qui vous êtes.");
  });

  /* ----- notifications ----- */

  function notify(message) {
    var host = document.getElementById("psc-toasts");
    if (!host) return;
    var el = document.createElement("div");
    el.className = "toast align-items-center border-0 show";
    el.setAttribute("role", "status");
    el.innerHTML =
      '<div class="d-flex"><div class="toast-body"></div>' +
      '<button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast" aria-label="Fermer"></button></div>';
    el.querySelector(".toast-body").textContent = message;
    host.appendChild(el);
    setTimeout(function () { el.remove(); }, 5000);
  }
  window.pscNotify = notify;

  /* ----- utilitaires ----- */

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[2]) : null;
  }

  /* ----- HTMX : signaler les échecs plutôt que de rester muet ----- */

  document.body.addEventListener("htmx:responseError", function (event) {
    if (event.detail.xhr.status === 409) return; // identité manquante, déjà traité
    notify("La mise à jour a échoué. Réessayez dans un instant.");
  });
  document.body.addEventListener("htmx:sendError", function () {
    notify("Connexion perdue. Vérifiez votre réseau.");
  });

  /* ----- une action à la fois -----
     Sans cela, un double clic sur « Je participe » ou « Supprimer » part
     deux fois. On ignore la seconde demande plutôt que de désactiver le
     bouton, ce qui lui ferait perdre le focus. */

  var inFlight = new WeakSet();

  document.body.addEventListener("htmx:beforeRequest", function (event) {
    var el = event.detail.elt;
    if (inFlight.has(el)) {
      event.preventDefault();
      return;
    }
    inFlight.add(el);
    el.setAttribute("data-psc-busy", "");
    el.setAttribute("aria-busy", "true");
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    var el = event.detail.elt;
    inFlight.delete(el);
    el.removeAttribute("data-psc-busy");
    el.removeAttribute("aria-busy");
  });

  /* ----- où va le focus après un échange -----
     Sans cela, celui qui navigue au clavier retombe en haut de page à
     chaque carte retournée en formulaire. */

  document.body.addEventListener("htmx:afterSwap", function (event) {
    var target = event.detail.target;
    if (!target || !target.querySelector) return;

    // Le filtrage du calendrier remplace la liste à chaque frappe : y porter
    // le focus arracherait le curseur du champ de recherche.
    var trigger = event.detail.requestConfig && event.detail.requestConfig.elt;
    if (trigger && trigger.closest && trigger.closest("#calendar-filters")) return;

    var first = target.querySelector("[data-autofocus]");
    if (first) {
      first.focus();
      return;
    }
    if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  });

  /* ----- annoncer ce qui vient de se passer -----
     Le serveur pose un en-tête HX-Trigger ; le message atterrit dans la zone
     aria-live, donc lu à voix haute autant qu'affiché. */

  document.body.addEventListener("psc:said", function (event) {
    if (event.detail && event.detail.message) notify(event.detail.message);
  });
})();
