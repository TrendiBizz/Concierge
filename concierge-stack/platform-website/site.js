(function () {
  var nav = document.getElementById('nav');
  var scrollBtn = document.getElementById('scrollToTop');
  var menuToggle = document.getElementById('menuToggle');
  var mobileMenu = document.getElementById('mobileMenu');

  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  // "Log in" links go to our own app (Twenty CRM at crm.trendibizz.com).
  // To use another address, set window.CONCIERGE_APP_URL before this script loads.
  var appUrl = window.CONCIERGE_APP_URL || 'https://crm.trendibizz.com/';
  document.querySelectorAll('a[data-app-link]').forEach(function (a) { a.setAttribute('href', appUrl); });

  function onScroll() {
    var y = window.scrollY;
    if (scrollBtn) {
      if (y > 300) scrollBtn.classList.remove('opacity-0', 'pointer-events-none');
      else scrollBtn.classList.add('opacity-0', 'pointer-events-none');
    }
    if (nav) nav.classList.toggle('shadow-lg', y > 50);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  if (scrollBtn) scrollBtn.addEventListener('click', function () {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });

  if (menuToggle && mobileMenu) {
    menuToggle.addEventListener('click', function () {
      var open = mobileMenu.classList.toggle('hidden') === false;
      menuToggle.setAttribute('aria-expanded', String(open));
    });
  }

  // Scroll reveal
  var items = document.querySelectorAll('.reveal');
  function show(el) { el.classList.add('in'); }
  if ('IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { show(entry.target); observer.unobserve(entry.target); }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });
    items.forEach(function (el) { observer.observe(el); });
  } else {
    items.forEach(show);
  }
})();

// Chat widget (served by our own API at chat.trendibizz.com). It loads only on the real site, so local and
// VM copies stay quiet. Set window.CONCIERGE_CHAT_OFF = true to disable it, or window.CONCIERGE_CHAT_ON = true
// to force it on another host (that host must also be in the tenant's allowed origins).
(function () {
  if (window.CONCIERGE_CHAT_OFF || window.__ccWidgetLoaded) return;
  var host = window.location.hostname || '';
  var onRealSite = /(^|\.)trendibizz\.com$/i.test(host);
  if (!onRealSite && !window.CONCIERGE_CHAT_ON) return;
  var s = document.createElement('script');
  s.src = 'https://chat.trendibizz.com/widget.js';
  s.setAttribute('data-key', 'pk_8y_wsHO4StqCzd0yc2QNEKp0');
  s.defer = true;
  document.body.appendChild(s);
})();
