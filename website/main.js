/* deploy: refresh PAGESPEED_API_KEY binding 2026-10-26b */
(function () {
  "use strict";

  var T = window.TRENDI;
  if (!T) { return; }

  var biz = T.business;

  function money(n) {
    try {
      return new Intl.NumberFormat("en-NZ", { style: "currency", currency: biz.currency, maximumFractionDigits: 0 }).format(n);
    } catch (e) {
      return "$" + n;
    }
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) { Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); }); }
    if (text) { node.textContent = text; }
    return node;
  }

  // Preview banner
  if (T.previewMode) {
    var banner = el("div", { "class": "preview-banner", role: "status" },
      "Preview: prices, payment links and contact details are placeholders.");
    document.body.insertBefore(banner, document.body.firstChild);
  }

  // Fill business details
  document.querySelectorAll("[data-email]").forEach(function (a) {
    a.setAttribute("href", "mailto:" + biz.email);
    if (!a.textContent.trim()) { a.textContent = biz.email; }
  });
  document.querySelectorAll("[data-year]").forEach(function (n) { n.textContent = new Date().getFullYear(); });

  // Mobile menu
  var menuBtn = document.getElementById("menu-btn");
  var nav = document.getElementById("main-nav");
  if (menuBtn && nav) {
    menuBtn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.tagName === "A") { nav.classList.remove("open"); menuBtn.setAttribute("aria-expanded", "false"); }
    });
  }

  // Pricing (skip if server-rendered static HTML is present)
  var pricing = document.getElementById("pricing-box");
  if (pricing && pricing.getAttribute("data-static") === "true") {
    // Static HTML already has price, terms, includes and Stripe links for crawlers.
  } else if (pricing && T.plans && T.plans.length) {
    var tabs = el("div", { "class": "tabs", role: "tablist", "aria-label": "How to pay" });
    var panel = el("div", { role: "tabpanel", id: "plan-panel" });
    var selected = 0;

    function linkIsReal(url) {
      return url && url.indexOf("REPLACE") === -1;
    }

    function renderPanel() {
      var p = T.plans[selected];
      panel.innerHTML = "";

      var price = el("div", { "class": "price" }, money(p.price));
      price.appendChild(el("small", null, p.per));
      panel.appendChild(price);
      panel.appendChild(el("p", { "class": "terms" }, p.terms + " " + biz.taxNote));

      var list = el("ul", { "class": "ticks" });
      T.includes.forEach(function (item) { list.appendChild(el("li", null, item)); });
      panel.appendChild(list);

      var buy = el("a", { "class": "btn" }, p.cta);
      if (linkIsReal(p.stripeLink)) {
        buy.setAttribute("href", p.stripeLink);
      } else {
        // No live Stripe link yet: fall back to email so nothing is a dead button.
        buy.setAttribute("href", "mailto:" + biz.email + "?subject=" + encodeURIComponent("Trendi: " + p.cta));
      }
      panel.appendChild(buy);

      Array.prototype.forEach.call(tabs.children, function (b, i) {
        b.setAttribute("aria-selected", i === selected ? "true" : "false");
        b.setAttribute("tabindex", i === selected ? "0" : "-1");
      });
    }

    T.plans.forEach(function (p, i) {
      var b = el("button", { "class": "tab", role: "tab", type: "button", "aria-controls": "plan-panel" }, p.tab);
      b.addEventListener("click", function () { selected = i; renderPanel(); });
      b.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          selected = (selected + (e.key === "ArrowRight" ? 1 : T.plans.length - 1)) % T.plans.length;
          renderPanel();
          tabs.children[selected].focus();
        }
      });
      tabs.appendChild(b);
    });

    pricing.appendChild(tabs);
    pricing.appendChild(panel);
    renderPanel();
  }

  // Proof (only if real numbers are enabled)
  var proof = document.getElementById("proof");
  if (proof) {
    if (T.proof && T.proof.enabled) {
      var grid = proof.querySelector(".proof-grid");
      proof.querySelector("[data-proof-title]").textContent = T.proof.title;
      proof.querySelector("[data-proof-caption]").textContent = T.proof.caption;
      T.proof.stats.forEach(function (s) {
        var box = el("div", { "class": "stat" });
        box.appendChild(el("div", { "class": "small" }, s.label));
        box.appendChild(el("div", { "class": "big" }, s.from + " → " + s.to));
        box.appendChild(el("div", { "class": "small" }, "over " + s.period));
        grid.appendChild(box);
      });
    } else {
      proof.remove();
      document.querySelectorAll('a[href="#proof"]').forEach(function (a) { a.remove(); });
    }
  }

  // "Start with one sentence" form -> mailto + Gmail/Outlook/copy fallbacks
  var form = document.getElementById("start-form");
  // Referral code (partners, /partners): letters, digits and hyphens only, max 32 characters, upper case.
  function cleanRef(v) {
    return String(v || "").replace(/[^A-Za-z0-9-]/g, "").slice(0, 32).toUpperCase();
  }
  if (form) {
    try {
      var startParams = new URLSearchParams(window.location.search);
      if (startParams.get("site") && form.elements.site && !form.elements.site.value) {
        form.elements.site.value = startParams.get("site");
      }
      if (startParams.get("question") && form.elements.question && !form.elements.question.value) {
        form.elements.question.value = startParams.get("question");
      }
      if (startParams.get("ref") && form.elements.ref && !form.elements.ref.value) {
        form.elements.ref.value = cleanRef(startParams.get("ref"));
      }
    } catch (prefillErr) {}
    if (form.elements.ref) {
      form.elements.ref.addEventListener("input", function () {
        var v = cleanRef(form.elements.ref.value);
        if (v !== form.elements.ref.value) { form.elements.ref.value = v; }
      });
    }

    var fallbacks = document.getElementById("start-fallbacks");
    var gmailLink = document.getElementById("start-gmail");
    var outlookLink = document.getElementById("start-outlook");
    var copyBtn = document.getElementById("start-copy");
    var lastBody = "";

    function buildDraft() {
      var question = (form.elements.question && form.elements.question.value || "").trim();
      var site = (form.elements.site && form.elements.site.value || "").trim();
      var name = (form.elements.name && form.elements.name.value || "").trim();
      var siteLabel = site || "our site";
      var q = question || "…";
      var body = 'When someone asks ChatGPT "' + q + '", the answer should include ' + siteLabel + ".";
      if (name) { body += "\n\nName: " + name; }
      var ref = cleanRef(form.elements.ref && form.elements.ref.value);
      if (ref) { body += "\n\nReferral code: " + ref; }
      body += "\n";
      var subject = "Trendi for " + siteLabel;
      return { subject: subject, body: body, to: biz.email };
    }

    function wireFallbacks(draft) {
      lastBody = draft.body;
      var enc = encodeURIComponent;
      if (gmailLink) {
        gmailLink.href = "https://mail.google.com/mail/?view=cm&fs=1&to=" + enc(draft.to) +
          "&su=" + enc(draft.subject) + "&body=" + enc(draft.body);
      }
      if (outlookLink) {
        outlookLink.href = "https://outlook.office.com/mail/deeplink/compose?to=" + enc(draft.to) +
          "&subject=" + enc(draft.subject) + "&body=" + enc(draft.body);
      }
      if (fallbacks) { fallbacks.hidden = false; }
      if (copyBtn) { copyBtn.textContent = "copy it"; }
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var draft = buildDraft();
      wireFallbacks(draft);
      window.location.href = "mailto:" + draft.to +
        "?subject=" + encodeURIComponent(draft.subject) +
        "&body=" + encodeURIComponent(draft.body);
    });

    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var text = lastBody || buildDraft().body;
        var done = function () { copyBtn.textContent = "copied it"; };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(done).catch(function () {
            // Fallback for older browsers / denied clipboard
            var ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.position = "fixed";
            ta.style.left = "-9999px";
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand("copy"); } catch (err) {}
            document.body.removeChild(ta);
            done();
          });
        } else {
          done();
        }
      });
    }
  }


  // Hero: cycle platform names then AI (FirstIndex-style flash). Comma lives in .flip text.
  (function initFlip() {
    var flip = document.querySelector(".hero h1 .flip");
    if (!flip) { return; }
    var words = ["ChatGPT", "Perplexity", "Gemini", "Claude", "Copilot", "Google", "Bing", "AI"];
    var i = words.length - 1;
    var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var busy = false;

    function show(word) {
      flip.textContent = word;
    }

    async function cycleOnce() {
      if (busy || still) { return; }
      busy = true;
      for (var n = 0; n < words.length; n++) {
        i = (i + 1) % words.length;
        flip.classList.add("is-flash");
        await new Promise(function (r) { setTimeout(r, 80); });
        show(words[i]);
        flip.classList.remove("is-flash");
        await new Promise(function (r) { setTimeout(r, 340); });
      }
      busy = false;
    }

    async function loop() {
      if (still) { return; }
      while (true) {
        await cycleOnce();
        await new Promise(function (r) { setTimeout(r, 1600); });
      }
    }

    flip.addEventListener("mouseenter", function () {
      if (!busy) { cycleOnce(); }
    });

    show(words[i]);
    loop();
  })();


  var header = document.querySelector('header.site');
  function headerState() { if (header) header.classList.toggle('scrolled', scrollY > 8); }
  addEventListener('scroll', headerState, { passive: true }); headerState();
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && nav && nav.classList.contains('open')) {
      nav.classList.remove('open'); menuBtn.setAttribute('aria-expanded', 'false'); menuBtn.focus();
    }
  });
  // Forms report progress and field errors without replacing tool handlers.
  document.querySelectorAll('form').forEach(function (f) {
    f.addEventListener('invalid', function (e) {
      var field = e.target, id = (field.id || field.name || 'field') + '-error';
      var error = document.getElementById(id);
      if (!error) { error = el('p', { id: id, 'class': 'form-error', role: 'alert' }); field.parentNode.appendChild(error); }
      error.textContent = field.validationMessage;
      field.setAttribute('aria-invalid', 'true'); field.setAttribute('aria-describedby', id);
    }, true);
    f.addEventListener('input', function (e) {
      if (e.target.validity && e.target.validity.valid) {
        e.target.removeAttribute('aria-invalid');
        var err = document.getElementById(e.target.getAttribute('aria-describedby'));
        if (err && err.classList.contains('form-error')) { err.remove(); e.target.removeAttribute('aria-describedby'); }
      }
    });
  });
  document.querySelectorAll('#site-check-out, #security-check-out, #robots-out').forEach(function (output) {
    var runner = output.previousElementSibling;
    if (!runner || runner.tagName !== 'FORM') return;
    var button = runner.querySelector('button[type=submit]');
    runner.addEventListener('submit', function () {
      button.style.minWidth = button.offsetWidth + 'px';
      button.textContent = 'Checking…'; button.disabled = true; runner.setAttribute('aria-busy', 'true');
      setTimeout(settle, 0);
    });
    function settle() {
      var pending = /^(Checking|Fetching|Running light security check)/.test(output.textContent.trim());
      if (pending) return;
      button.textContent = 'Run the check'; button.disabled = false; runner.removeAttribute('aria-busy');
      output.querySelectorAll('.sec-badge').forEach(function (badge) {
        if (badge.querySelector('svg')) return;
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'ui-icon'); svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('viewBox', '0 0 20 20');
        svg.innerHTML = '<circle cx="10" cy="10" r="8"/><path d="M10 8v6"/><circle cx="10" cy="5" r="1.2" fill="currentColor" stroke="none"/>';
        badge.prepend(svg);
      });
      output.querySelectorAll('.snap-card:not(.cta-card)').forEach(function (card) {
        if (card.querySelector('details')) return;
        var details = el('details'), summary = el('summary', null, 'Why this matters');
        details.appendChild(summary);
        details.appendChild(el('p', null, 'This is a public signal for this check only. Confirm findings in context; it does not prove indexing, rankings, AI mentions or security.'));
        card.appendChild(details);
      });
      output.querySelectorAll('.bot-results li').forEach(function (item) {
        if (item.querySelector('details')) return;
        var explanation = item.querySelector('.fine');
        if (!explanation) return;
        var d = el('details'); d.appendChild(el('summary', null, 'Why this matters')); d.appendChild(explanation); item.appendChild(d);
      });
    }
    new MutationObserver(settle).observe(output, { childList: true, subtree: true });
  });

  // Service tabs on the homepage. The strip is hidden in the HTML, so without JavaScript all
  // three panels stay visible. With it: one panel at a time, arrow keys, and #seo / #pen-testing links.
  (function initServiceTabs() {
    var strip = document.querySelector('.svc-tabs');
    if (!strip) return;
    var tabs = Array.prototype.slice.call(strip.querySelectorAll('[role="tab"]'));
    var panels = tabs.map(function (t) { return document.getElementById(t.getAttribute('aria-controls')); });
    if (!tabs.length || panels.some(function (p) { return !p; })) return;
    strip.hidden = false;
    function select(i, focus) {
      tabs.forEach(function (t, j) {
        var on = i === j;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        panels[j].hidden = !on;
      });
      if (focus) tabs[i].focus();
    }
    function fromHash() {
      var h = location.hash.replace('#', '');
      for (var i = 0; i < tabs.length; i++) { if (tabs[i].getAttribute('data-hash') === h) return i; }
      return -1;
    }
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () {
        select(i);
        try { history.replaceState(null, '', i === 0 ? location.pathname : '#' + t.getAttribute('data-hash')); } catch (e) {}
      });
      t.addEventListener('keydown', function (e) {
        var next = -1;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (i + tabs.length - 1) % tabs.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = tabs.length - 1;
        if (next < 0) return;
        e.preventDefault();
        select(next, true);
      });
    });
    addEventListener('hashchange', function () { var i = fromHash(); if (i >= 0) select(i); });
    select(Math.max(fromHash(), 0));
  })();

  // Concierge sign-up: if a Stripe Payment Link is set in products.js, the plan button goes to Stripe.
  // Otherwise it stays an email link. Only real Stripe links are accepted.
  (function initConciergeCheckout() {
    var plans = T.concierge;
    if (!plans || plans.checkout === false) return;
    document.querySelectorAll('a[data-concierge-plan]').forEach(function (a) {
      var plan = plans[a.getAttribute('data-concierge-plan')];
      var url = plan && typeof plan.stripeLink === 'string' ? plan.stripeLink.trim() : '';
      if (url.indexOf('https://buy.stripe.com/') !== 0 || url.indexOf('REPLACE') !== -1) return;
      a.setAttribute('href', url);
      a.setAttribute('rel', 'noopener');
      var label = a.getAttribute('data-pay-label');
      if (label) a.textContent = label;
    });
  })();
})();
