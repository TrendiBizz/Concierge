/**
 * Trendi light security check UI — Pass / Review / Info results.
 */
(function () {
  "use strict";

  var form = document.getElementById("security-check-form");
  var out = document.getElementById("security-check-out");
  var modeEl = document.getElementById("security-check-mode");
  if (!form || !out) return;

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function normaliseInput(raw) {
    var s = String(raw || "").trim();
    if (!s) throw new Error("Enter a website");
    if (/^\/\//.test(s)) s = "https:" + s;
    if (!/^[a-z][a-z0-9+.-]*:/i.test(s)) s = "https://" + s;
    var u = new URL(s);
    if (u.protocol !== "http:" && u.protocol !== "https:") {
      throw new Error("Use an http(s) website");
    }
    if (!u.hostname) throw new Error("Enter a website");
    return { origin: u.origin, href: u.origin + "/", host: u.hostname };
  }

  function applyUrlField() {
    var el = form.elements.url;
    if (!el) return;
    var raw = (el.value || "").trim();
    if (!raw) return;
    try {
      el.value = normaliseInput(raw).href;
    } catch (err) {}
  }

  function bucketLabel(b) {
    if (b === "pass") return "Pass";
    if (b === "review") return "Review";
    return "Info";
  }

  function renderValue(item) {
    if (!item || item.value == null || item.value === "") return "";
    var full = String(item.value);
    var shown = item.valueShown != null ? String(item.valueShown) : full;
    var truncated = !!item.valueTruncated;
    if (!truncated) {
      return (
        '<p class="sec-value"><span class="sec-k">Value:</span> <code>' +
        esc(full) +
        "</code></p>"
      );
    }
    var id = "val-" + Math.random().toString(36).slice(2, 9);
    return (
      '<p class="sec-value"><span class="sec-k">Value:</span> <code id="' +
      id +
      '-short">' +
      esc(shown) +
      '</code><code id="' +
      id +
      '-full" hidden>' +
      esc(full) +
      '</code> <button type="button" class="btn ghost sec-expand" data-expand="' +
      id +
      '" aria-expanded="false">Show full (' +
      esc(String(item.valueLength || full.length)) +
      " chars)</button></p>"
    );
  }

  function renderCheck(item) {
    var html = '<article class="sec-item sec-' + esc(item.bucket || "info") + '">';
    html +=
      '<header class="sec-item-head"><span class="sec-badge">' +
      esc(bucketLabel(item.bucket)) +
      "</span> <strong>" +
      esc(item.title) +
      "</strong></header>";
    if (item.meaning) {
      html +=
        '<details><summary>Why this matters</summary><p>' +
        esc(item.meaning) +
        "</p></details>";
    }
    if (item.result) {
      html +=
        '<p><span class="sec-k">What we found:</span> ' + esc(item.result) + "</p>";
    }
    html += renderValue(item);
    if (item.nextStep) {
      html +=
        '<p><span class="sec-k">What to do:</span> ' + esc(item.nextStep) + "</p>";
    }
    html += "</article>";
    return html;
  }

  function renderGroup(title, items, emptyMsg) {
    var html = '<section class="snap-card sec-group">';
    html += "<h2>" + esc(title) + " (" + items.length + ")</h2>";
    if (!items.length) {
      html += "<p class='fine'>" + esc(emptyMsg) + "</p>";
    } else {
      items.forEach(function (item) {
        html += renderCheck(item);
      });
    }
    html += "</section>";
    return html;
  }

  function render(data) {
    var groups = data.groups || {
      pass: (data.checks || []).filter(function (c) {
        return c.bucket === "pass";
      }),
      review: (data.checks || []).filter(function (c) {
        return c.bucket === "review";
      }),
      info: (data.checks || []).filter(function (c) {
        return c.bucket === "info";
      }),
    };

    var html = "";
    html += '<section class="snap-card">';
    html += "<h2>Result for " + esc(data.url || "") + "</h2>";
    html +=
      '<p class="sec-product-note"><strong>Light check — not a penetration test.</strong> ' +
      esc(
        data.productNote ||
          "This is a public hygiene pass only. It is not Trendi’s penetration testing product, not a compliance audit, and not a hack-proof guarantee."
      ) +
      ' <a href="/penetration-testing">Get a pen-test quote</a>.</p>';
    html +=
      '<p class="fine">' +
      esc(data.honesty || "") +
      "</p>";
    var c = data.counts || {
      pass: groups.pass.length,
      review: groups.review.length,
      info: groups.info.length,
    };
    html +=
      '<p class="sec-summary"><span class="sec-badge sec-pass">Pass ' +
      esc(String(c.pass)) +
      '</span> <span class="sec-badge sec-review">Review ' +
      esc(String(c.review)) +
      '</span> <span class="sec-badge sec-info">Info ' +
      esc(String(c.info)) +
      "</span></p>";
    html += "</section>";

    html += renderGroup(
      "Review",
      groups.review || [],
      "Nothing marked for review in this light pass."
    );
    html += renderGroup("Pass", groups.pass || [], "No pass items in this run.");
    html += renderGroup("Info", groups.info || [], "No info items in this run.");

    html += '<section class="snap-card cta-card"><h2>Need a deeper test?</h2>';
    html +=
      "<p>Paid <a href=\"/penetration-testing\">penetration testing</a> is a separate scoped engagement with a written quote in USD. This light check does not replace it.</p>";
    html +=
      '<p class="cta-row"><a class="btn" href="/penetration-testing">Penetration testing</a> ';
    html +=
      '<a class="btn ghost" href="/tools/site-check">Site snapshot (SEO)</a></p>';
    html += "</section>";

    if (data.warnings && data.warnings.length) {
      html +=
        '<p class="fine">Notes: ' + esc(data.warnings.join(" · ")) + "</p>";
    }
    out.innerHTML = html;

    if (modeEl) {
      modeEl.hidden = false;
      modeEl.textContent =
        data.mode === "server"
          ? "Mode: server (/api/security-check)"
          : "Mode: " + (data.mode || "unknown");
    }

    out.querySelectorAll("[data-expand]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-expand");
        var shortEl = document.getElementById(id + "-short");
        var fullEl = document.getElementById(id + "-full");
        if (!shortEl || !fullEl) return;
        var open = btn.getAttribute("aria-expanded") === "true";
        if (open) {
          shortEl.hidden = false;
          fullEl.hidden = true;
          btn.setAttribute("aria-expanded", "false");
          btn.textContent =
            "Show full (" + (fullEl.textContent || "").length + " chars)";
        } else {
          shortEl.hidden = true;
          fullEl.hidden = false;
          btn.setAttribute("aria-expanded", "true");
          btn.textContent = "Show less";
        }
      });
    });
  }

  function renderError(msg, extra) {
    var html =
      '<section class="snap-card"><h2>Could not finish the check</h2><p>' +
      esc(msg) +
      "</p>";
    if (extra) html += "<p class='fine'>" + esc(extra) + "</p>";
    html +=
      "<p>Try again in a moment, or email <a data-email href='#'>admin@trendibizz.com</a> with your URL if the tool stays down.</p></section>";
    out.innerHTML = html;
    if (window.trendiBindEmails) window.trendiBindEmails();
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    applyUrlField();
    var target;
    try {
      target = normaliseInput(form.elements.url.value);
      form.elements.url.value = target.href;
    } catch (err) {
      renderError(err.message || "Invalid website");
      return;
    }
    var aiBox = null;
    if (window.TrendiUI && typeof window.TrendiUI.aiStatus === "function") {
      out.textContent = "";
      var statusCard = document.createElement("section");
      statusCard.className = "snap-card";
      out.appendChild(statusCard);
      aiBox = window.TrendiUI.aiStatus(statusCard).thinking([
        "Checking HTTPS and TLS redirects",
        "Inspecting HTTP security headers",
        "Probing common exposed paths",
      ]);
      window.setTimeout(function () { if (aiBox) aiBox.step(0, "done"); }, 500);
      window.setTimeout(function () { if (aiBox) aiBox.step(1, "done"); }, 1100);
    } else {
      out.innerHTML = "<p class='fine'>Running light security check…</p>";
    }
    fetch("/api/security-check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: target.href }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) {
            var err = new Error(data.message || data.error || "api_error");
            err.status = res.status;
            err.data = data;
            throw err;
          }
          if (aiBox) { aiBox.done(); aiBox = null; }
          data.mode = data.mode || "server";
          render(data);
        });
      })
      .catch(function (err) {
        if (aiBox) { aiBox.step(2, "failed"); aiBox.done(); aiBox = null; }
        if (err.status === 429) {
          renderError(
            err.message || "Rate limited",
            "Limit is 5 checks per hour per IP."
          );
          return;
        }
        renderError(err.message || "Request failed");
      });
  });

  var urlEl = form.elements.url;
  if (urlEl) {
    urlEl.addEventListener("blur", applyUrlField);
    var params = new URLSearchParams(location.search);
    var pre = params.get("url") || params.get("site");
    if (pre) {
      urlEl.value = pre;
      applyUrlField();
    }
  }
})();
