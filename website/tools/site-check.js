/**
 * Trendi Site snapshot — client render + API / limited-mode fallback.
 * Tries POST /api/site-check (server). On failure: limited CORS fetches + paste fallbacks.
 * Never claims ranks or AI mentions. PSI deep-link always available.
 */
(function () {
  "use strict";

  var form = document.getElementById("site-check-form");
  var out = document.getElementById("site-check-out");
  var modeEl = document.getElementById("site-check-mode");
  var pastePanel = document.getElementById("site-check-paste");
  if (!form || !out) return;

  var SEARCH_BOTS = [
    { key: "googlebot", name: "Googlebot", patterns: [/googlebot/i] },
    { key: "bingbot", name: "Bingbot", patterns: [/bingbot/i] },
    { key: "oaiSearchBot", name: "OAI-SearchBot", patterns: [/oai-searchbot/i] },
    { key: "perplexityBot", name: "PerplexityBot", patterns: [/perplexitybot/i] },
    { key: "claudeSearchBot", name: "Claude-SearchBot", patterns: [/claude-searchbot/i] },
  ];

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Only https:// links may be rendered as hrefs (defence in depth: links come
  // from our own worker today, but a javascript: URL must never reach an href).
  function safeHref(u) {
    var s = String(u == null ? "" : u).trim();
    return /^https:\/\//i.test(s) ? s : "#";
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
    var path = u.pathname && u.pathname !== "/" ? u.pathname : "/";
    return {
      origin: u.origin,
      path: path,
      href: u.origin + (path === "/" ? "/" : path),
      host: u.hostname,
    };
  }

  function applyUrlField() {
    var el = form.elements.url;
    if (!el) return;
    var raw = (el.value || "").trim();
    if (!raw) return;
    try {
      var n = normaliseInput(raw);
      el.value = n.href;
    } catch (err) {
      /* leave as typed until submit */
    }
  }

  function buildLinks(pageUrl, host) {
    var enc = encodeURIComponent(pageUrl);
    var domain = String(host || "").replace(/^www\./, "");
    return {
      psi: "https://pagespeed.web.dev/analysis?url=" + enc,
      rrt: "https://search.google.com/test/rich-results?url=" + enc,
      gsc: "https://search.google.com/search-console",
      ga4: "https://analytics.google.com/",
      bing: "https://www.bing.com/webmasters",
      ahrefs: "https://ahrefs.com/backlink-checker?input=" + encodeURIComponent(domain),
      semrush: "https://www.semrush.com/",
      answerThePublic: "https://answerthepublic.com/",
      trends: "https://trends.google.com/",
      similarWeb:
        "https://chromewebstore.google.com/detail/similarweb-traffic-rank-w/hoklmmgfncapjnnelbajcjehmjhikoii",
      schemaValidator: "https://validator.schema.org/",
    };
  }

  function parseRobots(text) {
    var lines = text.split(/\r?\n/);
    var groups = [];
    var cur = null;
    var sitemaps = [];
    lines.forEach(function (raw) {
      var line = raw.replace(/#.*/, "").trim();
      if (!line) return;
      var m = line.match(/^(user-agent|allow|disallow|sitemap)\s*:\s*(.*)$/i);
      if (!m) return;
      var k = m[1].toLowerCase();
      var v = m[2].trim();
      if (k === "user-agent") {
        cur = { ua: v, rules: [] };
        groups.push(cur);
      } else if (k === "sitemap") {
        sitemaps.push(v);
      } else if (cur) {
        cur.rules.push({ type: k, path: v });
      }
    });
    return { groups: groups, sitemaps: sitemaps };
  }

  function matchGroup(groups, bot) {
    var star = null;
    var exact = null;
    groups.forEach(function (g) {
      if (g.ua === "*") star = g;
      bot.patterns.forEach(function (re) {
        if (re.test(g.ua)) exact = g;
      });
      if (g.ua.toLowerCase() === bot.name.toLowerCase()) exact = g;
    });
    return exact || star;
  }

  function rootAllowed(group) {
    if (!group) {
      return { status: "unknown" };
    }
    var rules = group.rules.filter(function (r) {
      return r.type === "allow" || r.type === "disallow";
    });
    var disallowAll = rules.some(function (r) {
      return r.type === "disallow" && (r.path === "/" || r.path === "/*");
    });
    var allowAll = rules.some(function (r) {
      return r.type === "allow" && (r.path === "/" || r.path === "/*" || r.path === "");
    });
    var emptyDisallowOnly =
      rules.length &&
      rules.every(function (r) {
        return r.type === "disallow" && r.path === "";
      });
    if (disallowAll && !allowAll) return { status: "blocked" };
    if (emptyDisallowOnly || allowAll || rules.length === 0) return { status: "allowed" };
    if (rules.some(function (r) { return r.type === "disallow" && r.path; })) {
      return { status: "partial" };
    }
    return { status: "allowed" };
  }

  function analyseRobots(text) {
    var parsed = parseRobots(text || "");
    var robots = {};
    SEARCH_BOTS.forEach(function (bot) {
      robots[bot.key] = rootAllowed(matchGroup(parsed.groups, bot)).status;
    });
    return { robots: robots, sitemapHints: parsed.sitemaps };
  }

  function stripTags(s) {
    return String(s || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function parseOnPage(html) {
    var titleM = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
    var title = titleM ? stripTags(titleM[1]) : "";
    var metaM =
      html.match(
        /<meta[^>]+name=["']description["'][^>]+content=["']([^"']*)["'][^>]*>/i
      ) ||
      html.match(
        /<meta[^>]+content=["']([^"']*)["'][^>]+name=["']description["'][^>]*>/i
      );
    var meta = metaM ? metaM[1].trim() : "";
    var canonM =
      html.match(/<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["'][^>]*>/i) ||
      html.match(/<link[^>]+href=["']([^"']+)["'][^>]+rel=["']canonical["'][^>]*>/i);
    var ogM =
      html.match(
        /<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']*)["'][^>]*>/i
      ) ||
      html.match(
        /<meta[^>]+content=["']([^"']*)["'][^>]+property=["']og:title["'][^>]*>/i
      );
    var h1s = html.match(/<h1\b[^>]*>/gi) || [];
    var schemaTypes = [];
    var re = /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi;
    var m;
    while ((m = re.exec(html))) {
      try {
        collectTypes(JSON.parse(m[1].trim()), schemaTypes);
      } catch (e) {}
    }
    var uniq = [];
    schemaTypes.forEach(function (t) {
      if (uniq.indexOf(t) === -1) uniq.push(t);
    });
    return {
      title: title,
      titleLen: title.length,
      meta: meta,
      metaLen: meta.length,
      h1Count: h1s.length,
      canonical: canonM ? canonM[1].trim() : null,
      ogTitle: ogM ? ogM[1].trim() : null,
      schemaTypes: uniq.slice(0, 40),
    };
  }

  function collectTypes(node, out) {
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach(function (n) {
        collectTypes(n, out);
      });
      return;
    }
    if (node["@type"]) {
      var t = node["@type"];
      if (Array.isArray(t)) {
        t.forEach(function (x) {
          out.push(String(x));
        });
      } else out.push(String(t));
    }
    if (node["@graph"]) collectTypes(node["@graph"], out);
  }

  function buildBuckets(data) {
    var https = data.https;
    var status = data.status;
    var robots = data.robots || {};
    var sitemap = data.sitemap || {};
    var onPage = data.onPage || {};
    var indexed = "amber";
    if (!https || status >= 400 || !status) indexed = "red";
    else if (robots.googlebot === "blocked" || robots.bingbot === "blocked") indexed = "red";
    else if (
      (robots.googlebot === "allowed" || robots.googlebot === "unknown") &&
      (robots.bingbot === "allowed" || robots.bingbot === "unknown") &&
      sitemap.found
    ) {
      indexed = "green";
    }
    var found = "amber";
    if (!onPage.title) found = "red";
    else if (
      onPage.titleLen >= 15 &&
      onPage.titleLen <= 60 &&
      onPage.metaLen >= 50 &&
      onPage.metaLen <= 160 &&
      onPage.h1Count === 1
    ) {
      found = "green";
    }
    return { indexed: indexed, found: found, mentioned: "unknown" };
  }

  function bucketClass(v) {
    if (v === "green") return "snap-bucket green";
    if (v === "red") return "snap-bucket red";
    if (v === "unknown") return "snap-bucket unknown";
    return "snap-bucket amber";
  }

  function botClass(status) {
    if (status === "allowed") return "bot-allowed";
    if (status === "blocked") return "bot-blocked";
    return "bot-unknown";
  }

  function flagLen(len, min, max, label) {
    if (!len) return label + ": missing";
    if (len < min) return label + ": short (" + len + ")";
    if (len > max) return label + ": long (" + len + ")";
    return label + ": " + len + " chars";
  }

  function render(data) {
    var links = data.links || buildLinks(data.url, data.origin || data.url);
    var buckets = data.buckets || buildBuckets(data);
    var onPage = data.onPage || {};
    var robots = data.robots || {};
    var sitemap = data.sitemap || {};
    var llms = data.llmsTxt || {};
    var psi = data.psi || {};
    var schema = data.schemaTypes || [];
    var missing = data.missingCommonSchema || [];
    var mode = data.mode || "server";

    if (modeEl) {
      modeEl.hidden = false;
      modeEl.textContent =
        mode === "server"
          ? "Mode: server (full snapshot via /api/site-check)"
          : "Mode: limited (browser CORS / paste — CSP or CORS may block some fetches until the Pages Function is deployed)";
    }

    var html = "";
    html += '<p class="fine honesty">' + esc(data.honesty || "Public technical snapshot only — not rankings. No AI mention check. No ranking promises.") + "</p>";

    html += '<div class="snap-buckets" aria-label="Soft readiness buckets">';
    html +=
      '<div class="' +
      bucketClass(buckets.indexed) +
      '"><strong>Indexed</strong><span>' +
      esc(buckets.indexed) +
      "</span><p class=\"fine\">Can crawlers reach you?</p></div>";
    html +=
      '<div class="' +
      bucketClass(buckets.found) +
      '"><strong>Found</strong><span>' +
      esc(buckets.found) +
      "</span><p class=\"fine\">On-page signals we can see</p></div>";
    html +=
      '<div class="' +
      bucketClass(buckets.mentioned) +
      '"><strong>Mentioned</strong><span>unknown</span><p class=\"fine\">Not checked in this snapshot</p></div>';
    html += "</div>";

    html += '<section class="snap-card"><h2>Snapshot</h2>';
    html +=
      "<ul class=\"snap-list\"><li><strong>URL</strong> " +
      esc(data.url) +
      "</li><li><strong>HTTPS</strong> " +
      (data.https ? "yes" : "no") +
      "</li><li><strong>Status</strong> " +
      esc(data.status || "—") +
      "</li>";
    if (data.xRobotsTag) {
      html += "<li><strong>x-robots-tag</strong> " + esc(data.xRobotsTag) + "</li>";
    }
    html += "</ul></section>";

    html += '<section class="snap-card"><h2>Indexed readiness</h2>';
    html += '<ul class="bot-results">';
    SEARCH_BOTS.forEach(function (b) {
      var st = robots[b.key] || "unknown";
      html +=
        '<li class="' +
        botClass(st) +
        '"><strong>' +
        esc(b.name) +
        "</strong>: " +
        esc(String(st).toUpperCase()) +
        "</li>";
    });
    html += "</ul>";
    html +=
      "<p><strong>Sitemap:</strong> " +
      (sitemap.found
        ? "found" +
          (sitemap.url ? " (" + esc(sitemap.url) + ")" : "") +
          (sitemap.urlCount != null ? " · ~" + esc(sitemap.urlCount) + " URLs (capped)" : "")
        : "missing or unreachable") +
      "</p>";
    html +=
      "<p><strong>llms.txt:</strong> " +
      (llms.found ? "present" : "not found") +
      ' <span class="fine">— ' +
      esc(llms.note || "Optional; Google ignores for rankings.") +
      "</span></p>";
    html +=
      '<p class="fine"><a href="/tools/robots-ai-check">Open AI robots checker →</a></p></section>';

    html += '<section class="snap-card"><h2>On-page signals</h2>';
    html += '<div class="serp-preview" aria-label="Rough SERP-style preview">';
    html +=
      '<p class="serp-url">' +
      esc((data.url || "").replace(/^https?:\/\//, "").slice(0, 60)) +
      "</p>";
    html +=
      '<p class="serp-title">' +
      esc((onPage.title || "(no title)").slice(0, 60)) +
      "</p>";
    html +=
      '<p class="serp-desc">' +
      esc((onPage.meta || "(no meta description)").slice(0, 160)) +
      "</p>";
    html += "</div>";
    html += "<ul class=\"snap-list\">";
    html +=
      "<li>" +
      esc(flagLen(onPage.titleLen, 15, 60, "Title")) +
      "</li>";
    html +=
      "<li>" +
      esc(flagLen(onPage.metaLen, 50, 160, "Meta description")) +
      "</li>";
    html += "<li><strong>H1 count</strong> " + esc(onPage.h1Count) + "</li>";
    html +=
      "<li><strong>Canonical</strong> " +
      (onPage.canonical ? esc(onPage.canonical) : "missing") +
      "</li>";
    if (onPage.ogTitle) {
      html += "<li><strong>og:title</strong> " + esc(onPage.ogTitle) + "</li>";
    }
    html += "</ul></section>";

    html += '<section class="snap-card"><h2>Structured data</h2>';
    if (schema.length) {
      html +=
        "<p>JSON-LD types found: <strong>" +
        esc(schema.join(", ")) +
        "</strong></p>";
    } else {
      html += "<p>No JSON-LD <code>@type</code> values detected on this URL.</p>";
    }
    if (missing.length) {
      html +=
        '<p class="fine">Common service-business types not seen (absence only): ' +
        esc(missing.join(", ")) +
        "</p>";
    }
    html +=
      '<p class="fine"><a href="' +
      esc(safeHref(links.rrt)) +
      '" target="_blank" rel="noopener">Google Rich Results Test ↗</a></p></section>';

    html += '<section class="snap-card"><h2>Speed &amp; vitals</h2>';
    if (psi.available) {
      html += "<ul class=\"snap-list\">";
      html +=
        "<li><strong>Performance (mobile)</strong> " +
        esc(psi.performance != null ? psi.performance : "—") +
        "</li>";
      html +=
        "<li><strong>SEO category</strong> " +
        esc(psi.seo != null ? psi.seo : "—") +
        "</li>";
      if (psi.lcp) html += "<li><strong>LCP</strong> " + esc(psi.lcp) + "</li>";
      if (psi.cls) html += "<li><strong>CLS</strong> " + esc(psi.cls) + "</li>";
      if (psi.inp) html += "<li><strong>INP</strong> " + esc(psi.inp) + "</li>";
      html += "</ul>";
    } else {
      html +=
        '<p class="snap-amber">PageSpeed scores not loaded here' +
        (psi.note ? " — " + esc(psi.note) : " — API key not configured or limited mode") +
        ".</p>";
    }
    html +=
      '<p><a class="btn ghost" href="' +
      esc(safeHref(links.psi)) +
      '" target="_blank" rel="noopener">Open PageSpeed Insights ↗</a></p></section>';

    html += '<section class="snap-card"><h2>What we can’t see yet</h2>';
    html +=
      '<p class="fine">Rankings, impressions and traffic need owner tools. Connect these yourself — Trendi uses them after you grant access.</p>';
    html += '<div class="chip-row">';
    html += chip(links.gsc, "Google Search Console");
    html += chip(links.ga4, "Google Analytics 4");
    html += chip(links.bing, "Bing Webmaster");
    html += "</div></section>";

    html += '<section class="snap-card"><h2>Explore yourself</h2>';
    html += '<div class="chip-row">';
    html += chip(links.ahrefs, "Ahrefs backlink peek");
    html += chip(links.semrush, "Semrush");
    html += chip(links.similarWeb, "SimilarWeb extension");
    html += chip(links.answerThePublic, "AnswerThePublic");
    html += chip(links.trends, "Google Trends");
    html += chip(links.rrt, "Rich Results Test");
    html += chip(links.psi, "PageSpeed UI");
    html += "</div></section>";

    html += '<section class="snap-card cta-card"><h2>Where Trendi helps</h2>';
    html +=
      "<p>Public checks show gaps in <strong>Indexed</strong> and <strong>Found</strong> readiness. Rankings and AI mentions need your Search Console (and steady work). Trendi does that work for you — no ranking promises.</p>";
    var sitePrefill = encodeURIComponent(
      (data.origin || data.url || "").replace(/^https?:\/\//, "").replace(/\/$/, "")
    );
    html +=
      '<p class="cta-row"><a class="btn" href="/?site=' +
      sitePrefill +
      '#start">Start with one sentence</a> ';
    html +=
      '<a class="btn ghost" href="/ai-visibility">Indexed · Found · Mentioned</a></p>';
    html += "</section>";

    if (data.warnings && data.warnings.length) {
      html +=
        '<p class="fine">Notes: ' +
        esc(data.warnings.join(" · ")) +
        "</p>";
    }

    out.innerHTML = html;
    if (pastePanel) pastePanel.hidden = mode === "server";
  }

  function chip(href, label) {
    return (
      '<a class="chip" href="' +
      esc(safeHref(href)) +
      '" target="_blank" rel="noopener">' +
      esc(label) +
      " ↗</a>"
    );
  }

  function tryServer(target) {
    return fetch("/api/site-check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url: target.href }),
    }).then(function (res) {
      if (res.status === 404) throw new Error("no_api");
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error(data.message || data.error || "api_error");
          err.data = data;
          err.status = res.status;
          throw err;
        }
        data.mode = data.mode || "server";
        return data;
      });
    });
  }

  function limitedFromFetches(target) {
    var warnings = [];
    var result = {
      mode: "limited",
      url: target.href,
      origin: target.origin,
      https: target.origin.indexOf("https:") === 0,
      status: 0,
      robots: {
        googlebot: "unknown",
        bingbot: "unknown",
        oaiSearchBot: "unknown",
        perplexityBot: "unknown",
        claudeSearchBot: "unknown",
      },
      sitemap: { found: false, url: null, urlCount: 0 },
      llmsTxt: {
        found: false,
        note: "Optional file; Google Search ignores llms.txt for rankings and AI Overviews.",
      },
      onPage: {
        title: "",
        titleLen: 0,
        meta: "",
        metaLen: 0,
        h1Count: 0,
        canonical: null,
        ogTitle: null,
      },
      schemaTypes: [],
      missingCommonSchema: ["Organization", "WebSite", "Service"],
      psi: {
        available: false,
        note: "Use the PageSpeed Insights link — API runs only in server mode.",
      },
      links: buildLinks(target.href, target.host),
      warnings: warnings,
      honesty:
        "Limited mode: browser could not use /api/site-check. Public snapshot only — not rankings. Paste robots/HTML below if fetches fail (CSP/CORS).",
    };

    var robotsP = fetch(target.origin + "/robots.txt", { mode: "cors" })
      .then(function (r) {
        if (!r.ok) throw new Error("robots " + r.status);
        return r.text();
      })
      .then(function (t) {
        var a = analyseRobots(t);
        result.robots = a.robots;
        return a.sitemapHints;
      })
      .catch(function () {
        warnings.push("robots.txt blocked or missing (try paste)");
        return [];
      });

    var htmlP = fetch(target.href, { mode: "cors" })
      .then(function (r) {
        result.status = r.status;
        result.url = r.url || target.href;
        result.https = String(result.url).indexOf("https:") === 0;
        if (!r.ok) warnings.push("Page HTTP " + r.status);
        return r.text();
      })
      .then(function (t) {
        var p = parseOnPage(t);
        result.onPage = {
          title: p.title,
          titleLen: p.titleLen,
          meta: p.meta,
          metaLen: p.metaLen,
          h1Count: p.h1Count,
          canonical: p.canonical,
          ogTitle: p.ogTitle,
        };
        result.schemaTypes = p.schemaTypes;
        var lower = p.schemaTypes.map(function (x) {
          return x.toLowerCase();
        });
        result.missingCommonSchema = ["Organization", "WebSite", "Service"].filter(
          function (t) {
            return lower.indexOf(t.toLowerCase()) === -1;
          }
        );
      })
      .catch(function () {
        warnings.push("HTML fetch blocked (try paste)");
      });

    var llmsP = fetch(target.origin + "/llms.txt", { mode: "cors" })
      .then(function (r) {
        if (r.ok) return r.text();
        throw new Error("no");
      })
      .then(function (t) {
        if (t && t.trim()) result.llmsTxt.found = true;
      })
      .catch(function () {});

    return robotsP
      .then(function (hints) {
        var urls = (hints || []).concat([
          target.origin + "/sitemap.xml",
          target.origin + "/sitemap_index.xml",
        ]);
        var chain = Promise.resolve(false);
        urls.forEach(function (u) {
          chain = chain.then(function (done) {
            if (done) return true;
            return fetch(u, { mode: "cors" })
              .then(function (r) {
                if (!r.ok) return false;
                return r.text().then(function (t) {
                  if (!/<urlset|<sitemapindex/i.test(t)) return false;
                  var count = Math.min((t.match(/<url\b/gi) || []).length, 200);
                  result.sitemap = { found: true, url: u, urlCount: count };
                  return true;
                });
              })
              .catch(function () {
                return false;
              });
          });
        });
        return chain;
      })
      .then(function () {
        return Promise.all([htmlP, llmsP]);
      })
      .then(function () {
        result.buckets = buildBuckets(result);
        result.warnings = warnings;
        return result;
      });
  }

  function applyPaste(target) {
    var robotsPaste = (form.elements.robots_paste && form.elements.robots_paste.value) || "";
    var htmlPaste = (form.elements.html_paste && form.elements.html_paste.value) || "";
    return limitedFromFetches(target).then(function (data) {
      if (robotsPaste.trim()) {
        var a = analyseRobots(robotsPaste);
        data.robots = a.robots;
        data.warnings = (data.warnings || []).filter(function (w) {
          return w.indexOf("robots") === -1;
        });
        data.warnings.push("robots from paste");
      }
      if (htmlPaste.trim()) {
        var p = parseOnPage(htmlPaste);
        data.onPage = {
          title: p.title,
          titleLen: p.titleLen,
          meta: p.meta,
          metaLen: p.metaLen,
          h1Count: p.h1Count,
          canonical: p.canonical,
          ogTitle: p.ogTitle,
        };
        data.schemaTypes = p.schemaTypes;
        data.status = data.status || 200;
        data.warnings.push("HTML from paste");
      }
      data.buckets = buildBuckets(data);
      data.mode = "limited";
      return data;
    });
  }

  form.elements.url.addEventListener("blur", applyUrlField);

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var raw = (form.elements.url && form.elements.url.value) || "";
    var target;
    try {
      target = normaliseInput(raw);
      if (form.elements.url) form.elements.url.value = target.href;
    } catch (err) {
      out.innerHTML =
        '<p class="fine">' +
        esc(err.message || "Enter a site (e.g. trendibizz.com). https:// is added if you leave it off.") +
        "</p>";
      return;
    }
    var aiBox = null;
    var aiTimer = null;
    if (window.TrendiUI && typeof window.TrendiUI.aiStatus === "function") {
      out.textContent = "";
      var statusHost = document.createElement("div");
      out.appendChild(statusHost);
      aiBox = window.TrendiUI.aiStatus(statusHost).thinking([
        "Fetching robots.txt and sitemap",
        "Reading homepage signals",
        "Checking schema and crawl readiness"
      ]);
      aiTimer = setTimeout(function () { if (aiBox) aiBox.step(0, "done"); }, 450);
    } else {
      out.innerHTML = '<p class="fine">Checking…</p>';
    }
    if (modeEl) modeEl.hidden = true;

    var hasPaste =
      ((form.elements.robots_paste && form.elements.robots_paste.value) || "").trim() ||
      ((form.elements.html_paste && form.elements.html_paste.value) || "").trim();

    var run = hasPaste
      ? applyPaste(target)
      : tryServer(target).catch(function (err) {
          if (err.status === 429) {
            if (aiTimer) clearTimeout(aiTimer);
            if (aiBox) { aiBox.done(); aiBox = null; }
            out.innerHTML =
              '<p class="fine">' +
              esc((err.data && err.data.message) || "Rate limited — try again later.") +
              "</p>";
            return null;
          }
          if (pastePanel) pastePanel.hidden = false;
          return limitedFromFetches(target);
        });

    run
      .then(function (data) {
        if (aiTimer) clearTimeout(aiTimer);
        if (!data) return;
        if (aiBox) { aiBox.step(0, "done"); aiBox.step(1, "done"); aiBox.step(2, "done"); aiBox.done(); }
        render(data);
      })
      .catch(function (err) {
        if (aiTimer) clearTimeout(aiTimer);
        if (aiBox) aiBox.done();
        out.innerHTML =
          '<p class="fine">Could not complete check. ' +
          esc(err.message || "") +
          " Paste robots.txt / homepage HTML below and re-check.</p>";
        if (pastePanel) pastePanel.hidden = false;
      });
  });

  // Prefill from ?url=
  try {
    var params = new URLSearchParams(location.search);
    if (params.get("url") && form.elements.url) {
      form.elements.url.value = params.get("url");
    }
  } catch (e) {}
})();
