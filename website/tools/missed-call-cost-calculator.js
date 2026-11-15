/* Missed-call cost calculator — the arithmetic, kept separate from the page so it can be tested.
 *
 * Deliberately no industry averages are baked in. "The average job value for a plumber" varies by
 * roughly ten times between a tap washer and a bathroom rebuild, so a published average would be a
 * number we invented, presented as a fact. The calculator therefore does arithmetic on the visitor's
 * own numbers and says so on the page.
 *
 * Exposed for tests through module.exports when it is loaded by Node, and attached to window for the
 * page. No dependency, no build step.
 */
(function (root) {
  'use strict';

  var WEEKS_PER_MONTH = 52 / 12; // 4.333…  — a calendar month, not "four weeks"

  /* Parse a user-typed number, tolerating the decorations people actually type: currency symbols,
   * thousands separators, spaces and a trailing percent. Anything that is not a number after that is
   * rejected outright rather than mined for digits — the earlier parseFloat-with-strip version turned
   * a hostile `?missed=<script>alert(1)</script>` into a confident 1 missed call a week. */
  function numberOr(value, fallback) {
    if (typeof value === 'number') return Number.isFinite(value) ? value : fallback;
    var text = String(value == null ? '' : value)
      .replace(/NZ\$|\$|%/gi, '')
      .replace(/[,_ ]/g, '')
      .trim();
    if (!/^[-+]?\d+(\.\d+)?$/.test(text)) return fallback;
    var parsed = parseFloat(text);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  /* The whole calculation, in one place.
   *   missedPerWeek — calls that rang out or were abandoned, per week
   *   jobValue      — what an average booked job is worth, in the visitor's currency
   *   conversionPct — of enquiries you do answer, how many become booked work (%)
   */
  function calculate(input) {
    input = input || {};
    var missedPerWeek = clamp(numberOr(input.missedPerWeek, 0), 0, 10000);
    var jobValue = clamp(numberOr(input.jobValue, 0), 0, 10000000);
    var conversionPct = clamp(numberOr(input.conversionPct, 0), 0, 100);

    var conversion = conversionPct / 100;
    var lostPerWeek = missedPerWeek * jobValue * conversion;
    var lostPerMonth = lostPerWeek * WEEKS_PER_MONTH;
    var lostPerYear = lostPerWeek * 52;
    var callsPerMonth = missedPerWeek * WEEKS_PER_MONTH;

    return {
      missedPerWeek: missedPerWeek,
      jobValue: jobValue,
      conversionPct: conversionPct,
      callsPerMonth: callsPerMonth,
      lostPerWeek: lostPerWeek,
      lostPerMonth: lostPerMonth,
      lostPerYear: lostPerYear,
      // The assumption made explicit: answering a call does not guarantee a booking.
      note: 'Assumes a missed call converts at the same rate as an answered one (' + conversionPct + '%).'
    };
  }

  function money(amount, currency) {
    var rounded = Math.round(amount);
    var text = String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (rounded < 0 ? '-' : '') + (currency || 'NZ$') + text;
  }

  /* Readable share links: the numbers live in the query string, so a calculation can be sent to a
   * colleague or quoted in a proposal without an account or a server round trip. */
  function toQuery(input) {
    var params = [];
    if (input.missedPerWeek != null) params.push('missed=' + encodeURIComponent(Math.round(numberOr(input.missedPerWeek, 0))));
    if (input.jobValue != null) params.push('value=' + encodeURIComponent(Math.round(numberOr(input.jobValue, 0))));
    if (input.conversionPct != null) params.push('close=' + encodeURIComponent(numberOr(input.conversionPct, 0)));
    if (input.trade) params.push('trade=' + encodeURIComponent(input.trade));
    return params.join('&');
  }

  function fromQuery(search) {
    var params = new URLSearchParams(search || '');
    var input = {};
    if (params.has('missed')) input.missedPerWeek = numberOr(params.get('missed'), 0);
    if (params.has('value')) input.jobValue = numberOr(params.get('value'), 0);
    if (params.has('close')) input.conversionPct = numberOr(params.get('close'), 0);
    if (params.has('trade')) input.trade = String(params.get('trade')).slice(0, 40);
    return input;
  }

  var api = {
    WEEKS_PER_MONTH: WEEKS_PER_MONTH,
    calculate: calculate,
    money: money,
    toQuery: toQuery,
    fromQuery: fromQuery
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.TrendiMissedCalls = api;

  /* --- page wiring -------------------------------------------------------------------
   * Kept in this file rather than inline because the site's CSP allows no inline script.
   * Everything below is inert when the module is loaded by Node for tests.
   */
  function wire() {
    if (typeof document === 'undefined') return;
    var form = document.getElementById('mc-form');
    if (!form) return;
    var fields = {
      missedPerWeek: document.getElementById('mc-missed'),
      jobValue: document.getElementById('mc-value'),
      conversionPct: document.getElementById('mc-close')
    };
    var trade = document.getElementById('mc-trade');
    var out = {
      week: document.getElementById('mc-week'),
      month: document.getElementById('mc-month'),
      year: document.getElementById('mc-year'),
      calls: document.getElementById('mc-calls'),
      assumption: document.getElementById('mc-assumption'),
      share: document.getElementById('mc-share')
    };

    function read() {
      return {
        missedPerWeek: fields.missedPerWeek.value,
        jobValue: fields.jobValue.value,
        conversionPct: fields.conversionPct.value,
        trade: trade ? trade.value : ''
      };
    }

    function render() {
      var input = read();
      var result = calculate(input);
      out.week.textContent = money(result.lostPerWeek);
      out.month.textContent = money(result.lostPerMonth);
      out.year.textContent = money(result.lostPerYear);
      out.calls.textContent = result.callsPerMonth.toFixed(0);
      out.assumption.textContent = result.note;
      var query = toQuery(input);
      var url = window.location.origin + window.location.pathname + (query ? '?' + query : '');
      out.share.value = url;
      try {
        window.history.replaceState(null, '', query ? '?' + query : window.location.pathname);
      } catch (error) {
        /* replaceState is blocked in some embedded contexts; the calculation still works. */
      }
    }

    Object.keys(fields).forEach(function (key) {
      fields[key].addEventListener('input', render);
      fields[key].addEventListener('change', render);
    });
    if (trade) trade.addEventListener('change', render);

    var copy = document.getElementById('mc-copy');
    if (copy) {
      copy.addEventListener('click', function () {
        out.share.select();
        var done = function () {
          copy.textContent = 'Copied';
          window.setTimeout(function () { copy.textContent = 'Copy link'; }, 2000);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(out.share.value).then(done, function () { document.execCommand('copy'); done(); });
        } else {
          document.execCommand('copy');
          done();
        }
      });
    }

    var shared = fromQuery(window.location.search);
    if (shared.missedPerWeek != null) fields.missedPerWeek.value = shared.missedPerWeek;
    if (shared.jobValue != null) fields.jobValue.value = shared.jobValue;
    if (shared.conversionPct != null) fields.conversionPct.value = shared.conversionPct;
    if (shared.trade && trade) trade.value = shared.trade;
    render();
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', wire);
    } else {
      wire();
    }
  }
})(typeof window !== 'undefined' ? window : null);
