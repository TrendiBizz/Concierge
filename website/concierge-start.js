(function () {
  "use strict";
  var form = document.getElementById("concierge-start-form");
  if (!form) return;
  var result = document.getElementById("setup-review");
  var draft = document.getElementById("setup-draft");
  var email = document.getElementById("setup-email");
  var status = document.getElementById("setup-status");
  var plan = new URLSearchParams(location.search).get("plan");
  if (plan === "monthly" || plan === "yearly") form.elements.plan.value = plan;
  function resetReview() {
    result.hidden = true;
    draft.textContent = "";
    email.href = "mailto:admin@trendibizz.com";
    status.textContent = "";
  }
  form.addEventListener("input", resetReview);
  form.addEventListener("change", resetReview);
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var field = form.elements.website;
    field.setCustomValidity("");
    var url;
    try {
      var input = field.value.trim();
      url = new URL(/^[a-z][a-z0-9+.-]*:/i.test(input) ? input : "https://" + input);
      if (url.protocol !== "https:" || !url.hostname.includes(".") || url.username || url.password) throw new Error();
    } catch (_) {
      field.setCustomValidity("Enter your public website address, such as https://example.com.");
      field.reportValidity();
      return;
    }
    var values = new FormData(form);
    var channels = values.getAll("channel");
    var text = "Hello Trendi, I would like to set up Concierge.\n\n" +
      "Business: " + values.get("business").trim() + "\n" +
      "Website: " + url.href + "\n" +
      "Contact email: " + values.get("email").trim() + "\n" +
      "Plan interest: " + values.get("plan") + "\n" +
      "What I would like help with: " + (channels.join(", ") || "Please advise") + "\n\n" +
      "Business details and questions:\n" + values.get("details").trim();
    draft.textContent = text;
    email.href = "mailto:admin@trendibizz.com?subject=" + encodeURIComponent("Concierge setup request") + "&body=" + encodeURIComponent(text);
    result.hidden = false;
    status.textContent = "Your request is ready to review. Nothing has been sent.";
    result.focus();
  });
  form.elements.website.addEventListener("input", function () { this.setCustomValidity(""); });
  document.getElementById("setup-copy").addEventListener("click", function () {
    if (!navigator.clipboard) { status.textContent = "Select and copy the request shown below."; return; }
    navigator.clipboard.writeText(draft.textContent).then(function () {
      status.textContent = "Request copied. Paste it into an email to admin@trendibizz.com.";
    }).catch(function () { status.textContent = "Select and copy the request shown below."; });
  });
})();
