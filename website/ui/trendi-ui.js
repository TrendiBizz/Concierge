/*! Trendi UI: small vanilla ports of ideas from libraries we cannot drop into a static site.
 *
 *   toast()        idea from Sonner (MIT, (c) 2023 Emil Kowalski): stacked, swipe-to-dismiss, pauses on hover.
 *   sheet()        idea from Vaul (MIT, (c) 2023 Emil Kowalski): mobile bottom sheet, drag down to close.
 *   commandMenu()  idea from cmdk (MIT, (c) 2022 Paco Coursey): Cmd/Ctrl-K search. commandScore() below is
 *                  copied from cmdk's src/command-score.ts under its MIT licence (notice kept here).
 *   ticker()       idea from NumberFlow (MIT, (c) 2024 Maxwell Barvian): digits roll to the new value.
 *   aiStatus()     idea from Beautiful UI (MIT, (c) 2026 Shane Levine): thinking, streaming and approval states.
 *
 * Only commandScore is copied code; the rest is our own, written from each library's observed behaviour.
 * MIT notice for the copied part: Permission is hereby granted, free of charge, to any person obtaining a
 * copy of this software ... THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND. Full text:
 * https://github.com/pacocoursey/cmdk/blob/main/LICENSE.md
 *
 * Site rules this file keeps: no inline <style> or style="" (CSP style-src 'self'; only CSSOM writes),
 * every animation respects prefers-reduced-motion, styles live in /ui/trendi-ui.css on brand tokens.
 */
(function (root) {
  "use strict";

  // ------------------------------------------------------------------ pure logic (unit-tested in node)

  // cmdk command-score (copied, MIT): continuous matches score 1, word starts score high, gaps decay.
  var SCORE_CONTINUE_MATCH = 1, SCORE_SPACE_WORD_JUMP = 0.9, SCORE_NON_SPACE_WORD_JUMP = 0.8,
    SCORE_CHARACTER_JUMP = 0.17, SCORE_TRANSPOSITION = 0.1, PENALTY_SKIPPED = 0.999,
    PENALTY_CASE_MISMATCH = 0.9999, PENALTY_NOT_COMPLETE = 0.99;
  var IS_GAP_REGEXP = /[\\\/_+.#"@\[\(\{&]/, COUNT_GAPS_REGEXP = /[\\\/_+.#"@\[\(\{&]/g,
    IS_SPACE_REGEXP = /[\s-]/, COUNT_SPACE_REGEXP = /[\s-]/g;

  function commandScoreInner(string, abbreviation, lowerString, lowerAbbreviation, stringIndex, abbreviationIndex, memo) {
    if (abbreviationIndex === abbreviation.length) {
      return stringIndex === string.length ? SCORE_CONTINUE_MATCH : PENALTY_NOT_COMPLETE;
    }
    var key = stringIndex + "," + abbreviationIndex;
    if (memo[key] !== undefined) return memo[key];
    var abbreviationChar = lowerAbbreviation.charAt(abbreviationIndex);
    var index = lowerString.indexOf(abbreviationChar, stringIndex);
    var highScore = 0, score, transposedScore, wordBreaks, spaceBreaks;
    while (index >= 0) {
      score = commandScoreInner(string, abbreviation, lowerString, lowerAbbreviation, index + 1, abbreviationIndex + 1, memo);
      if (score > highScore) {
        if (index === stringIndex) {
          score *= SCORE_CONTINUE_MATCH;
        } else if (IS_GAP_REGEXP.test(string.charAt(index - 1))) {
          score *= SCORE_NON_SPACE_WORD_JUMP;
          wordBreaks = string.slice(stringIndex, index - 1).match(COUNT_GAPS_REGEXP);
          if (wordBreaks && stringIndex > 0) score *= Math.pow(PENALTY_SKIPPED, wordBreaks.length);
        } else if (IS_SPACE_REGEXP.test(string.charAt(index - 1))) {
          score *= SCORE_SPACE_WORD_JUMP;
          spaceBreaks = string.slice(stringIndex, index - 1).match(COUNT_SPACE_REGEXP);
          if (spaceBreaks && stringIndex > 0) score *= Math.pow(PENALTY_SKIPPED, spaceBreaks.length);
        } else {
          score *= SCORE_CHARACTER_JUMP;
          if (stringIndex > 0) score *= Math.pow(PENALTY_SKIPPED, index - stringIndex);
        }
        if (string.charAt(index) !== abbreviation.charAt(abbreviationIndex)) score *= PENALTY_CASE_MISMATCH;
      }
      if ((score < SCORE_TRANSPOSITION && lowerString.charAt(index - 1) === lowerAbbreviation.charAt(abbreviationIndex + 1)) ||
          (lowerAbbreviation.charAt(abbreviationIndex + 1) === lowerAbbreviation.charAt(abbreviationIndex) &&
           lowerString.charAt(index - 1) !== lowerAbbreviation.charAt(abbreviationIndex))) {
        transposedScore = commandScoreInner(string, abbreviation, lowerString, lowerAbbreviation, index + 1, abbreviationIndex + 2, memo);
        if (transposedScore * SCORE_TRANSPOSITION > score) score = transposedScore * SCORE_TRANSPOSITION;
      }
      if (score > highScore) highScore = score;
      index = lowerString.indexOf(abbreviationChar, index + 1);
    }
    memo[key] = highScore;
    return highScore;
  }
  function formatInput(s) { return s.toLowerCase().replace(COUNT_SPACE_REGEXP, " "); }
  function commandScore(string, abbreviation, aliases) {
    string = aliases && aliases.length ? string + " " + aliases.join(" ") : string;
    return commandScoreInner(string, abbreviation, formatInput(string), formatInput(abbreviation), 0, 0, {});
  }

  /** Filter + rank items ({label, href, group?, keywords?}) for a query. Empty query keeps the given order. */
  function rankItems(items, query) {
    var q = String(query || "").trim();
    if (!q) return items.slice();
    return items
      .map(function (item, i) { return { item: item, i: i, s: commandScore(item.label, q, item.keywords || []) }; })
      .filter(function (r) { return r.s > 0; })
      .sort(function (a, b) { return b.s - a.s || a.i - b.i; })
      .map(function (r) { return r.item; });
  }

  // Vaul's release rule: upward drags snap back; a fast flick (> 0.4 px/ms) or a drag past 25% of the
  // sheet's height closes; anything else springs back.
  var SHEET_VELOCITY = 0.4, SHEET_CLOSE_FRACTION = 0.25;
  function sheetRelease(distance, height, velocity) {
    if (distance <= 0) return "reset";
    if (velocity > SHEET_VELOCITY) return "close";
    if (distance >= height * SHEET_CLOSE_FRACTION) return "close";
    return "reset";
  }

  // Sonner's stack: newest in front, three visible, older ones peek behind smaller; hover fans them out.
  var TOAST_VISIBLE = 3, TOAST_GAP = 14, TOAST_PEEK = 10, TOAST_LIFETIME = 4000, TOAST_SWIPE = 45;
  /** index 0 = newest. heights[] = rendered heights, newest first. */
  function toastLayout(index, heights, expanded) {
    var hidden = index >= TOAST_VISIBLE;
    if (expanded) {
      var y = 0;
      for (var k = 0; k < index; k++) y += (heights[k] || 0) + TOAST_GAP;
      return { y: -y, scale: 1, hidden: hidden };
    }
    return { y: -index * TOAST_PEEK, scale: 1 - index * 0.05, hidden: hidden };
  }
  function toastDismissed(swipe, velocity) { return Math.abs(swipe) >= TOAST_SWIPE || velocity > 0.11; }

  /** Split a formatted number into rolling digits and fixed symbols (NumberFlow keeps symbols still). */
  function tickerParts(text) {
    return String(text).split("").map(function (ch) {
      return /[0-9]/.test(ch) ? { digit: true, value: +ch } : { digit: false, value: ch };
    });
  }

  // ------------------------------------------------------------------ DOM helpers

  var doc = root.document;
  function reducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  function h(tag, attrs, kids) {
    var n = doc.createElement(tag);
    if (attrs) for (var k in attrs) { if (attrs[k] != null) n.setAttribute(k, attrs[k]); }
    (kids || []).forEach(function (c) { n.appendChild(typeof c === "string" ? doc.createTextNode(c) : c); });
    return n;
  }
  var uid = 0;
  function nextId(p) { uid += 1; return "tui-" + p + "-" + uid; }

  // ------------------------------------------------------------------ toast (Sonner idea)

  var toastState = null;
  function toastRegion() {
    if (toastState) return toastState;
    var list = h("ol", { "class": "tui-toasts" });
    var region = h("section", {
      "class": "tui-toast-region", "aria-label": "Notifications alt+T", tabindex: "-1",
      "aria-live": "polite", "aria-relevant": "additions text", "aria-atomic": "false"
    }, [list]);
    doc.body.appendChild(region);
    toastState = { region: region, list: list, items: [], expanded: false };
    function setExpanded(v) { toastState.expanded = v; layoutToasts(); }
    region.addEventListener("pointerenter", function () { setExpanded(true); });
    region.addEventListener("pointerleave", function () { setExpanded(false); });
    region.addEventListener("focusin", function () { setExpanded(true); });
    region.addEventListener("focusout", function (e) { if (!region.contains(e.relatedTarget)) setExpanded(false); });
    doc.addEventListener("keydown", function (e) {
      if (e.altKey && e.code === "KeyT") { e.preventDefault(); region.focus(); }
    });
    doc.addEventListener("visibilitychange", function () {
      toastState.items.forEach(function (t) { doc.hidden ? t.pause() : t.resume(); });
    });
    return toastState;
  }
  function layoutToasts() {
    var s = toastState, heights = s.items.map(function (t) { return t.el.offsetHeight; });
    s.items.forEach(function (t, i) {
      var l = toastLayout(i, heights, s.expanded);
      t.el.style.transform = "translateY(" + (l.y + t.swipe) + "px) scale(" + l.scale + ")";
      t.el.style.zIndex = String(100 - i);
      t.el.classList.toggle("tui-hidden", l.hidden);
      t.el.setAttribute("aria-hidden", l.hidden ? "true" : "false");
    });
    s.items.forEach(function (t) { s.expanded ? t.pause() : t.resume(); });
  }
  /** toast("Copied", {type: "success"|"error"|"info", duration, action: {label, onClick}}) */
  function toast(message, opts) {
    opts = opts || {};
    var s = toastRegion();
    var close = h("button", { type: "button", "class": "tui-toast-close", "aria-label": "Close notification" }, ["×"]);
    var kids = [h("p", { "class": "tui-toast-text" }, [String(message)])];
    if (opts.action) {
      var act = h("button", { type: "button", "class": "tui-toast-action" }, [opts.action.label]);
      act.addEventListener("click", function () { opts.action.onClick(); dismiss(); });
      kids.push(act);
    }
    kids.push(close);
    var el = h("li", { "class": "tui-toast", "data-type": opts.type || "info",
      role: opts.type === "error" ? "alert" : "status" }, kids);
    var remaining = opts.duration || TOAST_LIFETIME, timer = null, started = 0;
    var t = { el: el, swipe: 0,
      pause: function () { if (timer) { clearTimeout(timer); timer = null; remaining -= Date.now() - started; } },
      resume: function () { if (!timer && remaining > 0 && !s.expanded && !doc.hidden) { started = Date.now(); timer = setTimeout(dismiss, remaining); } }
    };
    function dismiss() {
      t.pause(); remaining = 0;
      var i = s.items.indexOf(t); if (i < 0) return;
      s.items.splice(i, 1);
      el.classList.add("tui-leaving");
      setTimeout(function () { el.remove(); }, reducedMotion() ? 0 : 200);
      layoutToasts();
    }
    close.addEventListener("click", dismiss);
    // Swipe sideways to dismiss (pointer events cover touch and mouse).
    var x0 = null, t0 = 0;
    el.addEventListener("pointerdown", function (e) {
      if (e.target.closest("button")) return;
      x0 = e.clientX; t0 = Date.now(); el.setPointerCapture(e.pointerId); el.classList.add("tui-dragging");
    });
    el.addEventListener("pointermove", function (e) {
      if (x0 === null) return;
      t.swipe = 0; el.style.translate = (e.clientX - x0) + "px 0";
    });
    el.addEventListener("pointerup", function (e) {
      if (x0 === null) return;
      var dx = e.clientX - x0, v = Math.abs(dx) / Math.max(1, Date.now() - t0);
      x0 = null; el.classList.remove("tui-dragging");
      if (toastDismissed(dx, v)) { el.classList.add(dx < 0 ? "tui-out-left" : "tui-out-right"); dismiss(); }
      else el.style.translate = "";
    });
    s.items.unshift(t);
    s.list.insertBefore(el, s.list.firstChild);
    layoutToasts();
    t.resume();
    return { dismiss: dismiss };
  }

  // ------------------------------------------------------------------ bottom sheet (Vaul idea)

  /** Open `content` (an element; pass a clone to keep the original in place) in a bottom sheet.
   *  Returns {close, el}. Native <dialog> gives the focus trap, Escape and top layer. */
  function sheet(content, opts) {
    opts = opts || {};
    var handle = h("div", { "class": "tui-sheet-handle", "aria-hidden": "true" });
    var body = h("div", { "class": "tui-sheet-body" }, [content]);
    var dlg = h("dialog", { "class": "tui-sheet", "aria-label": opts.label || "Menu" }, [handle, body]);
    doc.body.appendChild(dlg);
    var opener = doc.activeElement;
    dlg.showModal();
    doc.documentElement.classList.add("tui-scroll-lock");
    requestAnimationFrame(function () { dlg.classList.add("tui-open"); });
    var closed = false;
    function close() {
      if (closed) return; closed = true;
      dlg.classList.remove("tui-open");
      dlg.style.transform = "";
      setTimeout(function () {
        if (dlg.open) dlg.close();
        dlg.remove();
        doc.documentElement.classList.remove("tui-scroll-lock");
        if (opts.onClose) opts.onClose();
        if (opener && opener.focus) opener.focus();
      }, reducedMotion() ? 0 : 500);
    }
    dlg.addEventListener("cancel", function (e) { e.preventDefault(); close(); });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) close(); }); // backdrop click
    // Drag down from the handle or anywhere the content is scrolled to the top.
    var y0 = null, t0 = 0, dy = 0;
    dlg.addEventListener("pointerdown", function (e) {
      if (e.target === dlg || body.scrollTop > 0) return;
      y0 = e.clientY; t0 = Date.now(); dy = 0; dlg.classList.add("tui-dragging");
    });
    dlg.addEventListener("pointermove", function (e) {
      if (y0 === null) return;
      dy = e.clientY - y0;
      // Upward drag is damped, like Vaul: the sheet resists rather than detaching.
      dlg.style.transform = "translateY(" + (dy > 0 ? dy : -Math.sqrt(-dy)) + "px)";
    });
    function release() {
      if (y0 === null) return;
      var v = Math.abs(dy) / Math.max(1, Date.now() - t0);
      y0 = null; dlg.classList.remove("tui-dragging");
      if (sheetRelease(dy, dlg.offsetHeight, dy > 0 ? v : 0) === "close") close();
      else dlg.style.transform = "";
    }
    dlg.addEventListener("pointerup", release);
    dlg.addEventListener("pointercancel", release);
    if (opts.closeOnLink !== false) {
      body.addEventListener("click", function (e) { if (e.target.closest("a")) close(); });
    }
    return { close: close, el: dlg };
  }

  // ------------------------------------------------------------------ command menu (cmdk idea)

  /** commandMenu({items: [...]}) or commandMenu({indexUrl: "/ui/search-index.json"}). Cmd/Ctrl-K toggles. */
  function commandMenu(opts) {
    opts = opts || {};
    var items = opts.items || null, active = 0, shown = [];
    var listId = nextId("list");
    var input = h("input", { "class": "tui-cmdk-input", type: "text", role: "combobox", autocomplete: "off",
      "aria-expanded": "true", "aria-controls": listId, "aria-autocomplete": "list",
      placeholder: opts.placeholder || "Search pages…", "aria-label": "Search the site" });
    var list = h("ul", { "class": "tui-cmdk-list", id: listId, role: "listbox", "aria-label": "Results" });
    var empty = h("p", { "class": "tui-cmdk-empty", hidden: "" }, ["No pages match."]);
    var hint = h("p", { "class": "tui-cmdk-hint" }, ["↑↓ to move, Enter to open, Esc to close"]);
    var dlg = h("dialog", { "class": "tui-cmdk", "aria-label": "Search" }, [input, list, empty, hint]);
    doc.body.appendChild(dlg);

    function load() {
      if (items || !opts.indexUrl) return Promise.resolve(items || []);
      return root.fetch(opts.indexUrl).then(function (r) { return r.json(); })
        .then(function (data) { items = data.pages || []; return items; })
        .catch(function () { items = []; return items; });
    }
    function render() {
      shown = rankItems(items || [], input.value).slice(0, opts.max || 8);
      active = Math.min(active, Math.max(0, shown.length - 1));
      list.textContent = "";
      shown.forEach(function (item, i) {
        var li = h("li", { role: "option", id: listId + "-" + i, "class": "tui-cmdk-item",
          "aria-selected": i === active ? "true" : "false" },
          [h("span", { "class": "tui-cmdk-label" }, [item.label]),
           item.group ? h("span", { "class": "tui-cmdk-group" }, [item.group]) : null].filter(Boolean));
        li.addEventListener("pointermove", function () { if (active !== i) { active = i; render(); } });
        li.addEventListener("click", function () { go(item); });
        list.appendChild(li);
      });
      empty.hidden = shown.length > 0;
      if (shown.length) input.setAttribute("aria-activedescendant", listId + "-" + active);
      else input.removeAttribute("aria-activedescendant");
    }
    function go(item) { dlg.close(); if (item && item.href) root.location.assign(item.href); }
    function open() {
      if (dlg.open) return;
      input.value = ""; active = 0;
      dlg.showModal();
      load().then(render);
      input.focus();
    }
    input.addEventListener("input", function () { active = 0; render(); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); active = shown.length ? (active + 1) % shown.length : 0; render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); active = shown.length ? (active - 1 + shown.length) % shown.length : 0; render(); }
      else if (e.key === "Enter") { e.preventDefault(); go(shown[active]); }
    });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
    doc.addEventListener("keydown", function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault(); dlg.open ? dlg.close() : open();
      }
    });
    return { open: open, close: function () { dlg.close(); }, el: dlg };
  }

  // ------------------------------------------------------------------ ticker (NumberFlow idea)

  /** ticker(el, value, {format: Intl.NumberFormat options, locale}). Call again with a new value to roll. */
  function ticker(el, value, opts) {
    opts = opts || {};
    var fmt = new Intl.NumberFormat(opts.locale || "en-NZ", opts.format || {});
    var text = fmt.format(value);
    el.setAttribute("aria-label", text);
    if (reducedMotion() || !el.__tuiTicker && opts.animateFirst === false) {
      el.textContent = text; el.__tuiTicker = { text: text }; return;
    }
    var parts = tickerParts(text), prev = el.__tuiTicker;
    var view = h("span", { "class": "tui-ticker", "aria-hidden": "true" });
    var prevDigits = prev ? tickerParts(prev.text).filter(function (p) { return p.digit; }) : [];
    var digitCount = parts.filter(function (p) { return p.digit; }).length, d = 0;
    var reels = [];
    parts.forEach(function (p) {
      if (!p.digit) { view.appendChild(h("span", { "class": "tui-sym" }, [p.value])); return; }
      // Align old and new digits from the right, so units roll into units.
      var fromIndex = prevDigits.length - (digitCount - d);
      var from = fromIndex >= 0 ? prevDigits[fromIndex].value : 0;
      d += 1;
      var reel = h("span", { "class": "tui-reel" });
      for (var n = 0; n <= 9; n++) reel.appendChild(h("span", null, [String(n)]));
      reel.style.transform = "translateY(" + (-from * 10) + "%)";
      view.appendChild(h("span", { "class": "tui-digit" }, [reel]));
      reels.push({ reel: reel, to: p.value });
    });
    el.textContent = "";
    el.appendChild(view);
    el.__tuiTicker = { text: text };
    void view.offsetWidth; // commit start positions before the transition
    root.requestAnimationFrame(function () {
      reels.forEach(function (r) { r.reel.style.transform = "translateY(" + (-r.to * 10) + "%)"; });
    });
  }

  // ------------------------------------------------------------------ AI states (Beautiful UI idea)

  /** aiStatus(el) -> {thinking(steps), step(i, state), stream(text), approve({question, options}), done(msg)} */
  function aiStatus(el) {
    var started = Date.now(), clock = null;
    function reset(cls) { el.textContent = ""; el.className = "tui-ai " + cls; if (clock) { clearInterval(clock); clock = null; } }
    var api = {
      thinking: function (steps) {
        reset("tui-ai-thinking");
        el.setAttribute("aria-busy", "true");
        var head = h("p", { "class": "tui-ai-head" }, [h("span", { "class": "tui-ai-pulse", "aria-hidden": "true" }), "Working "]);
        var time = h("span", { "class": "tui-ai-time" }, ["0s"]);
        head.appendChild(time);
        var ol = h("ol", { "class": "tui-ai-steps" });
        (steps || []).forEach(function (s, i) { ol.appendChild(h("li", { "data-state": i === 0 ? "active" : "pending" }, [s])); });
        el.appendChild(head); el.appendChild(ol);
        started = Date.now();
        clock = setInterval(function () { time.textContent = Math.round((Date.now() - started) / 1000) + "s"; }, 1000);
        return api;
      },
      step: function (i, state) {
        var li = el.querySelectorAll(".tui-ai-steps li");
        if (li[i]) li[i].setAttribute("data-state", state || "done");
        if (state !== "failed" && li[i + 1] && li[i + 1].getAttribute("data-state") === "pending") li[i + 1].setAttribute("data-state", "active");
        return api;
      },
      /** Reveal text word by word with a caret; resolves when finished. Reduced motion shows it at once. */
      stream: function (text) {
        reset("tui-ai-stream");
        el.setAttribute("aria-busy", "true");
        var p = h("p", { "class": "tui-ai-text" }), caret = h("span", { "class": "tui-ai-caret", "aria-hidden": "true" });
        el.appendChild(p); el.appendChild(caret);
        var words = String(text).split(/(\s+)/), i = 0;
        return new Promise(function (resolve) {
          function finish() { p.textContent = text; caret.remove(); el.setAttribute("aria-busy", "false"); resolve(api); }
          if (reducedMotion()) return finish();
          (function tick() {
            if (i >= words.length) return finish();
            p.appendChild(doc.createTextNode(words[i++]));
            setTimeout(tick, 28);
          })();
        });
      },
      /** Human-in-the-loop card: question, options, Skip / Continue. Resolves with the chosen option or null. */
      approve: function (q) {
        reset("tui-ai-approve");
        el.setAttribute("aria-busy", "false");
        var chosen = null, name = nextId("opt");
        var fs = h("fieldset", { "class": "tui-ai-card" }, [h("legend", null, [q.question])]);
        if (q.step) fs.appendChild(h("p", { "class": "tui-ai-stepcount" }, [q.step]));
        var cont = h("button", { type: "button", "class": "btn tui-ai-continue", disabled: "" }, [q.continueLabel || "Continue"]);
        var skip = h("button", { type: "button", "class": "tui-ai-skip" }, [q.skipLabel || "Skip"]);
        (q.options || []).forEach(function (o, i) {
          var id = name + "-" + i, radio = h("input", { type: "radio", name: name, id: id, value: String(i) });
          radio.addEventListener("change", function () { chosen = o; cont.disabled = false; });
          fs.appendChild(h("label", { "class": "tui-ai-option", "for": id }, [radio, h("span", null, [o])]));
        });
        fs.appendChild(h("div", { "class": "tui-ai-actions" }, [skip, cont]));
        el.appendChild(fs);
        return new Promise(function (resolve) {
          cont.addEventListener("click", function () { resolve(chosen); });
          skip.addEventListener("click", function () { resolve(null); });
        });
      },
      done: function (msg) {
        reset("tui-ai-done");
        el.setAttribute("aria-busy", "false");
        if (msg) el.appendChild(h("p", null, [msg]));
        return api;
      }
    };
    return api;
  }

  var TrendiUI = {
    toast: toast, sheet: sheet, commandMenu: commandMenu, ticker: ticker, aiStatus: aiStatus,
    _logic: { commandScore: commandScore, rankItems: rankItems, sheetRelease: sheetRelease,
      toastLayout: toastLayout, toastDismissed: toastDismissed, tickerParts: tickerParts }
  };
  if (typeof module !== "undefined" && module.exports) module.exports = TrendiUI;
  else root.TrendiUI = TrendiUI;
})(typeof window !== "undefined" ? window : globalThis);
