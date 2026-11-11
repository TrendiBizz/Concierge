/* Public-site language switcher (Google machine translation, with feedback note). */
(function () {
  'use strict';
  var LANGS = [
    ['en','English'],['af','Afrikaans'],['ar','العربية'],['ca','Català'],['cs','Čeština'],['da','Dansk'],
    ['de','Deutsch'],['el','Ελληνικά'],['es','Español'],['fi','Suomi'],['fr','Français'],['he','עברית'],
    ['hu','Magyar'],['it','Italiano'],['ja','日本語'],['ko','한국어'],['nl','Nederlands'],['no','Norsk'],
    ['pl','Polski'],['pt','Português'],['ro','Română'],['ru','Русский'],['sr','Српски'],['sv','Svenska'],
    ['tr','Türkçe'],['uk','Українська'],['vi','Tiếng Việt'],['zh-CN','中文（简体）'],['zh-TW','中文（繁體）']
  ];
  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : '';
  }
  function current() {
    var c = getCookie('googtrans');
    var m = c && c.split('/').pop();
    return (m && m !== 'en') ? m : (localStorage.getItem('trendi.lang') || 'en');
  }
  function setLanguage(code) {
    localStorage.setItem('trendi.lang', code);
    var value = code === 'en' ? '/en/en' : '/en/' + code;
    document.cookie = 'googtrans=' + value + '; path=/';
    if (code === 'en') document.cookie = 'googtrans=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
    location.reload();
  }
  function build() {
    var wrap = document.createElement('div');
    wrap.id = 'trendi-lang';
    wrap.className = 'notranslate';
    wrap.innerHTML = '<button type="button" aria-expanded="false" aria-controls="trendi-lang-panel">🌐 <span>Language</span></button>' +
      '<div id="trendi-lang-panel" role="dialog" aria-label="Choose a language">' +
      '<p class="trendi-lang-note">Automated translation. We welcome corrections — <a href="mailto:admin@trendibizz.com?subject=Website%20translation%20feedback">tell us what to improve</a>.</p>' +
      '<label for="trendi-lang-select">Language</label><select id="trendi-lang-select"></select></div>';
    document.body.appendChild(wrap);
    var select = wrap.querySelector('select');
    LANGS.forEach(function (pair) {
      var option = document.createElement('option');
      option.value = pair[0]; option.textContent = pair[1];
      if (pair[0] === current()) option.selected = true;
      select.appendChild(option);
    });
    var button = wrap.querySelector('button');
    button.addEventListener('click', function () {
      var open = wrap.classList.toggle('open');
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    select.addEventListener('change', function () { setLanguage(select.value); });
  }
  window.googleTranslateElementInit = function () {
    new google.translate.TranslateElement({
      pageLanguage: 'en',
      includedLanguages: LANGS.map(function (pair) { return pair[0]; }).join(','),
      autoDisplay: false
    }, 'google_translate_element');
  };
  function loadGoogle() {
    var host = document.createElement('div');
    host.id = 'google_translate_element';
    host.style.display = 'none';
    document.body.appendChild(host);
    var script = document.createElement('script');
    script.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
    script.async = true;
    document.body.appendChild(script);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { build(); loadGoogle(); });
  else { build(); loadGoogle(); }
})();
