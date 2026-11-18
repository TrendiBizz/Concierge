(function () {
  "use strict";
  var form = document.getElementById("concierge-start-form");
  if (!form) return;
  var result = document.getElementById("setup-review");
  var draft = document.getElementById("setup-draft");
  var email = document.getElementById("setup-email");
  var status = document.getElementById("setup-status");
  var plan = new URLSearchParams(location.search).get("plan");
  // Monthly only; an old yearly query string is ignored (yearly billing is on request by email).
  if (plan === "monthly") form.elements.plan.value = plan;
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
    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;
    status.textContent = "Sending…";
    function showDraft(message) {
      if (button) button.disabled = false;
      result.hidden = false;
      status.textContent = message;
      result.focus();
    }
    fetch("/api/enquiry", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        kind: "concierge", email: values.get("email").trim(), name: values.get("business").trim(),
        website: url.href, message: values.get("details").trim(), plan: String(values.get("plan") || ""),
        channels: channels, trap: String(values.get("trap") || "")
      })
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) { return {ok: r.ok, data: data}; });
    }).then(function (res) {
      if (res.ok) {
        if (button) button.disabled = false;
        status.textContent = "Thanks — we have your request. We will reply to " + values.get("email").trim() + " within one business day.";
        form.reset();
        return;
      }
      showDraft((res.data && res.data.detail) || "We could not send that from here. Your request is ready to email instead.");
    }).catch(function () {
      showDraft("We could not send that from here. Your request is ready to email instead.");
    });
  });
  form.elements.website.addEventListener("input", function () { this.setCustomValidity(""); });
  document.getElementById("setup-copy").addEventListener("click", function () {
    if (!navigator.clipboard) { status.textContent = "Select and copy the request shown below."; return; }
    navigator.clipboard.writeText(draft.textContent).then(function () {
      status.textContent = "Request copied. Paste it into an email to admin@trendibizz.com.";
    }).catch(function () { status.textContent = "Select and copy the request shown below."; });
  });
})();
