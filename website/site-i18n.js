/* Self-hosted homepage language switcher: applies reviewed/machine translations
   from /site-i18n.json. No third-party scripts, so the site CSP stays strict. */
(function () {
  'use strict';
  if (location.pathname !== '/' && location.pathname !== '/index.html') return;
  var LANGS = [
    ['en','English'],['af','Afrikaans'],['ar','العربية'],['ca','Català'],['cs','Čeština'],['da','Dansk'],
    ['de','Deutsch'],['el','Ελληνικά'],['es','Español'],['fi','Suomi'],['fr','Français'],['he','עברית'],
    ['hu','Magyar'],['it','Italiano'],['ja','日本語'],['ko','한국어'],['nl','Nederlands'],['no','Norsk'],
    ['pl','Polski'],['pt-BR','Português (BR)'],['pt-PT','Português (PT)'],['ro','Română'],['ru','Русский'],
    ['sr','Српски'],['sv','Svenska'],['tr','Türkçe'],['uk','Українська'],['vi','Tiếng Việt'],
    ['zh-CN','中文（简体）'],['zh-TW','中文（繁體）']
  ];
  function chosen() {
    var query = new URLSearchParams(location.search).get('lang');
    if (query && LANGS.some(function (p) { return p[0] === query; })) return query;
    var saved = localStorage.getItem('trendi.lang');
    if (saved && LANGS.some(function (p) { return p[0] === saved; })) return saved;
    return 'en';
  }
  var locale = chosen();
  var dictionary = null;
  function translate(value) {
    if (!dictionary || locale === 'en') return null;
    var translated = dictionary[locale] && dictionary[locale][value];
    return translated && translated !== value ? translated : null;
  }
  function apply() {
    if (!dictionary || locale === 'en') return;
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
  fetch('/site-i18n.json', {cache: 'no-store'}).then(function (response) { return response.json(); }).then(function (data) {
    dictionary = data;
    build();
    apply();
  }).catch(function () { build(); });
})();
