/*
 * TrialScribe documentation site — small progressive-enhancement script.
 * No dependencies, no build step. Handles the mobile nav drawer only;
 * the site works fully without JavaScript.
 */
(function () {
  "use strict";

  var toggle = document.querySelector("[data-nav-toggle]");
  var sidebar = document.querySelector("[data-sidebar]");
  var scrim = document.querySelector("[data-nav-scrim]");

  if (!toggle || !sidebar) {
    return;
  }

  function openNav() {
    sidebar.classList.add("is-open");
    if (scrim) {
      scrim.classList.add("is-open");
    }
    toggle.setAttribute("aria-expanded", "true");
  }

  function closeNav() {
    sidebar.classList.remove("is-open");
    if (scrim) {
      scrim.classList.remove("is-open");
    }
    toggle.setAttribute("aria-expanded", "false");
  }

  toggle.addEventListener("click", function () {
    var isOpen = sidebar.classList.contains("is-open");
    if (isOpen) {
      closeNav();
    } else {
      openNav();
    }
  });

  if (scrim) {
    scrim.addEventListener("click", closeNav);
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeNav();
    }
  });

  // Close the drawer automatically when a nav link is chosen (mobile).
  sidebar.addEventListener("click", function (event) {
    if (event.target.closest("a")) {
      closeNav();
    }
  });
})();
