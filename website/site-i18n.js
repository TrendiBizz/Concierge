/* Public-site language switcher. Uses a self-hosted dictionary plus the
   Concierge translation endpoint (cached server-side). No third-party scripts. */
(function () {
  'use strict';
  var LANGS = [
    ['en','English'],['af','Afrikaans'],['ar','العربية'],['ca','Català'],['cs','Čeština'],['da','Dansk'],
    ['de','Deutsch'],['el','Ελληνικά'],['es','Español'],['fi','Suomi'],['fr','Français'],['he','עברית'],
    ['hu','Magyar'],['it','Italiano'],['ja','日本語'],['ko','한국어'],['nl','Nederlands'],['no','Norsk'],
    ['pl','Polski'],['pt-BR','Português (BR)'],['pt-PT','Português (PT)'],['ro','Română'],['ru','Русский'],
    ['sr','Српски'],['sv','Svenska'],['tr','Türkçe'],['uk','Українська'],['vi','Tiếng Việt'],
    ['zh-CN','中文（简体）'],['zh-TW','中文（繁體）']
  ];
  var API = 'https://chat.trendibizz.com/api/v1/translate';
  function chosen() {
    var query = new URLSearchParams(location.search).get('lang');
    if (query && LANGS.some(function (p) { return p[0] === query; })) return query;
    var saved = localStorage.getItem('trendi.lang');
    if (saved && LANGS.some(function (p) { return p[0] === saved; })) return saved;
    return 'en';
  }
  var locale = chosen();
  var dictionary = {};
  function translate(value) {
    if (locale === 'en') return null;
    var translated = dictionary[value];
    return translated && translated !== value ? translated : null;
  }
  function apply() {
    if (locale === 'en') return;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent || parent.closest('.notranslate')) continue;
      if (['SCRIPT','STYLE','TEXTAREA','INPUT','CODE'].indexOf(parent.tagName) >= 0) continue;
      var value = node.nodeValue || '';
      var trimmed = value.trim();
      var translated = translate(trimmed);
      if (translated) node.nodeValue = value.replace(trimmed, translated);
    }
    ['placeholder','aria-label','title','alt','content'].forEach(function (attribute) {
      document.querySelectorAll('[' + attribute + ']').forEach(function (element) {
        if (element.closest('.notranslate')) return;
        var value = element.getAttribute(attribute);
        if (!value) return;
        var translated = translate(value.trim());
        if (translated) element.setAttribute(attribute, translated);
      });
    });
  }
  function collect() {
    var values = [];
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent || parent.closest('.notranslate')) continue;
      if (['SCRIPT','STYLE','TEXTAREA','INPUT','CODE'].indexOf(parent.tagName) >= 0) continue;
      var value = (node.nodeValue || '').trim();
      if (value.length > 1 && value.length <= 300 && values.indexOf(value) < 0) values.push(value);
    }
    ['placeholder','aria-label','title','alt','content'].forEach(function (attribute) {
      document.querySelectorAll('[' + attribute + ']').forEach(function (element) {
        if (element.closest('.notranslate')) return;
        var value = (element.getAttribute(attribute) || '').trim();
        if (value.length > 1 && value.length <= 300 && values.indexOf(value) < 0) values.push(value);
      });
    });
    return values;
  }
  function loadCache() {
    try {
      var saved = JSON.parse(localStorage.getItem('trendi.i18n.' + locale) || '{}');
      Object.keys(saved).forEach(function (key) { if (!dictionary[key] && saved[key] !== key) dictionary[key] = saved[key]; });
    } catch (_) { /* ignore corrupt cache */ }
  }
  function saveCache() {
    try { localStorage.setItem('trendi.i18n.' + locale, JSON.stringify(dictionary)); } catch (_) { /* quota */ }
  }
  function wait(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }
  async function translateChunk(chunk) {
    var last = null;
    for (var attempt = 0; attempt < 3; attempt++) {
      try {
        var response = await fetch(API, {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({locale: locale, strings: chunk})});
        if (response.ok) return response.json();
        last = response.status;
        if (response.status !== 429 && response.status !== 503 && response.status !== 1015) break;
      } catch (_) { last = 'network'; }
      await wait(1500 * (attempt + 1));
    }
    return null;
  }
  async function translateMissing(values) {
    var missing = values.filter(function (value) { return !dictionary[value] || dictionary[value] === value; });
    for (var start = 0; start < missing.length; start += 80) {
      var chunk = missing.slice(start, start + 80);
      var data = await translateChunk(chunk);
      if (data) {
        Object.keys(data.strings || {}).forEach(function (key) { dictionary[key] = data.strings[key]; });
        saveCache();
        apply();
      }
      await wait(250);
    }
  }
  function build() {
    var wrap = document.createElement('div');
    wrap.id = 'trendi-lang';
    wrap.className = 'notranslate';
    wrap.innerHTML = '<button type="button" aria-expanded="false" aria-controls="trendi-lang-panel">🌐 <span>Language</span></button>' +
      '<div id="trendi-lang-panel" role="dialog" aria-label="Choose a language">' +
      '<p id="trendi-lang-note">Automated translation. We welcome corrections — <a href="mailto:admin@trendibizz.com?subject=Website%20translation%20feedback">tell us what to improve</a>.</p>' +
      '<label for="trendi-lang-select">Language</label><select id="trendi-lang-select"></select></div>';
    document.body.appendChild(wrap);
    var select = wrap.querySelector('select');
    LANGS.forEach(function (pair) {
      var option = document.createElement('option');
      option.value = pair[0]; option.textContent = pair[1];
      if (pair[0] === locale) option.selected = true;
      select.appendChild(option);
    });
    var button = wrap.querySelector('button');
    button.addEventListener('click', function () {
      var open = wrap.classList.toggle('open');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    select.addEventListener('change', function () {
      localStorage.setItem('trendi.lang', select.value);
      var url = new URL(location.href);
      url.searchParams.set('lang', select.value);
      location.href = url.toString();
    });
  }
  async function start() {
    if (locale === 'en') { build(); return; }
    try {
      var local = await fetch('/site-i18n.json', {cache: 'no-store'}).then(function (r) { return r.json(); });
      dictionary = (local[locale] || {});
    } catch (_) { dictionary = {}; }
    loadCache();
    build();
    var values = collect();
    await translateMissing(values);
    apply();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
