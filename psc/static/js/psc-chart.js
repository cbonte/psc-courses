/* Graphique des inscriptions. Les données viennent d'un endpoint JSON,
   plus aucun JavaScript n'est fabriqué dans les gabarits. */

(function () {
  "use strict";

  var canvas = document.getElementById("psc-chart");
  if (!canvas || typeof Chart === "undefined") return;

  var empty = document.getElementById("psc-chart-empty");

  function themeColors() {
    var styles = getComputedStyle(document.documentElement);
    return {
      grid: styles.getPropertyValue("--psc-line").trim() || "#d8e0e5",
      text: styles.getPropertyValue("--psc-muted").trim() || "#5d6d78"
    };
  }

  function withAlpha(hex, alpha) {
    var value = (hex || "#6c757d").replace("#", "");
    if (value.length !== 6) return hex;
    var r = parseInt(value.slice(0, 2), 16);
    var g = parseInt(value.slice(2, 4), 16);
    var b = parseInt(value.slice(4, 6), 16);
    return "rgba(" + r + ", " + g + ", " + b + ", " + alpha + ")";
  }

  fetch(canvas.dataset.url, { credentials: "same-origin" })
    .then(function (response) { return response.json(); })
    .then(function (payload) {
      var total = payload.datasets.reduce(function (sum, set) {
        return sum + set.data.reduce(function (a, b) { return a + b; }, 0);
      }, 0);

      if (!total) {
        canvas.classList.add("d-none");
        if (empty) empty.classList.remove("d-none");
        return;
      }

      var colors = themeColors();
      new Chart(canvas.getContext("2d"), {
        type: "bar",
        data: {
          labels: payload.labels,
          datasets: payload.datasets.map(function (set) {
            return {
              label: set.label,
              data: set.data,
              backgroundColor: withAlpha(set.color, 0.75),
              borderColor: set.color,
              borderWidth: 1,
              borderRadius: 3
            };
          })
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: colors.text } },
            y: {
              stacked: true,
              beginAtZero: true,
              ticks: { color: colors.text, precision: 0 },
              grid: { color: colors.grid }
            }
          },
          plugins: {
            legend: { labels: { color: colors.text, boxWidth: 12, boxHeight: 12 } },
            tooltip: { mode: "index", intersect: false }
          }
        }
      });
    })
    .catch(function () {
      canvas.classList.add("d-none");
      if (empty) {
        empty.textContent = "Les statistiques n'ont pas pu être chargées.";
        empty.classList.remove("d-none");
      }
    });
})();
