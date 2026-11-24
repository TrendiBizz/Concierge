/* Trendi's website-to-Concierge client. No credentials or customer data live here. */
(function () {
  "use strict";
  var requested = false;
  var status = document.querySelector("[data-concierge-status]");

  function say(message) { if (status) status.textContent = message; }
  function openAssistant() {
    if (window.__ccWidgetReady) {
      window.dispatchEvent(new Event("concierge:open"));
      return true;
    }
    // Compatibility with the currently deployed widget during the staged rollout.
    var root = document.getElementById("cc-root");
    var launcher = root && root.shadowRoot && root.shadowRoot.querySelector(".launcher");
    if (!launcher) return false;
    launcher.click();
    return true;
  }
  function finishOpen() {
    if (requested && openAssistant()) {
      requested = false;
      say("");
    }
  }
  window.addEventListener("concierge:ready", finishOpen);
  document.querySelectorAll("[data-concierge-open]").forEach(function (button) {
    button.addEventListener("click", function (event) {
      if (openAssistant()) { event.preventDefault(); return; }
      event.preventDefault();
      if (requested) return;
      var fallbackHref = button.getAttribute("href");
      requested = true;
      say("Opening Concierge…");
      var attempts = 0;
      var timer = window.setInterval(function () {
        finishOpen();
        if (!requested || ++attempts >= 20) {
          window.clearInterval(timer);
          if (requested) {
            requested = false;
            if (status) {
              say("Chat is unavailable right now. You can still request setup below or email admin@trendibizz.com.");
            } else if (fallbackHref && fallbackHref.charAt(0) === "/") {
              window.location.href = fallbackHref;
            }
          }
        }
      }, 250);
    });
  });

})();
