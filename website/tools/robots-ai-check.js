(function(){
 var form = typeof document !== 'undefined' ? document.getElementById('robots-form') : null;
 var out = typeof document !== 'undefined' ? document.getElementById('robots-out') : null;
 var BOTS = [
 {name:'Googlebot', patterns:[/googlebot/i], note:'Search crawler'},
 {name:'Bingbot', patterns:[/bingbot/i], note:'Search crawler'},
 {name:'OAI-SearchBot', patterns:[/oai-searchbot/i], note:'Search — OpenAI search indexing'},
 {name:'PerplexityBot', patterns:[/perplexitybot/i], note:'Search — Perplexity indexing'},
 {name:'Claude-SearchBot', patterns:[/claude-searchbot/i], note:'Search — Anthropic search'},
 {name:'ChatGPT-User', patterns:[/chatgpt-user/i], note:'User-triggered — fetches when a ChatGPT user asks; robots.txt may not apply'},
 {name:'Claude-User', patterns:[/claude-user/i], note:'User-triggered — fetches when a Claude user asks; robots.txt may not apply'},
 {name:'Perplexity-User', patterns:[/perplexity-user/i], note:'User-triggered — user-requested fetches; often ignores robots.txt'},
 {name:'Applebot-Extended', patterns:[/applebot-extended/i], note:'Training / Apple Intelligence policy — separate from Applebot search'},
 {name:'CCBot', patterns:[/ccbot/i], note:'Training — Common Crawl'},
 {name:'Bytespider', patterns:[/bytespider/i], note:'Training — ByteDance'},
 {name:'Meta-ExternalAgent', patterns:[/meta-externalagent/i], note:'Training / Meta AI fetching'},
 {name:'Amazonbot', patterns:[/amazonbot/i], note:'Search / Alexa-related crawling'},
 {name:'GPTBot (training)', patterns:[/gptbot/i], note:'Training crawler — separate from OAI-SearchBot and ChatGPT-User'},
 {name:'ClaudeBot (training)', patterns:[/claudebot/i], note:'Training crawler — separate from Claude-SearchBot and Claude-User'},
 {name:'Google-Extended', patterns:[/google-extended/i], note:'Training / Gemini grounding policy — separate from Googlebot'}
 ];
 // RFC 9309 evaluator, ported from seo/study/scripts/robots9309.py (the AI-crawler study's tested parser) so the tool and the study agree.
 // Groups: consecutive user-agent lines then rules; a user-agent line after rules starts a new group. All groups whose product
 // token matches (case-insensitive) are merged; else merged * groups; else no rules. Longest match wins, Allow wins ties; * and $ supported.
 // Only the first 500 KiB are parsed (RFC 9309 s2.5).
 var MAX_BYTES = 500 * 1024;
 function capBytes(text){
 if(typeof TextEncoder === 'undefined') return text;
 var b = new TextEncoder().encode(text);
 return b.length > MAX_BYTES ? new TextDecoder('utf-8').decode(b.subarray(0, MAX_BYTES)) : text;
 }
 function parseRobots(text){
 var groups = [], cur = null, inRules = false;
 String(text).split('\n').forEach(function(raw){
 var line = raw.split('#')[0].replace(/\r+$/,'');
 var m = line.match(/^\s*([A-Za-z-]+)\s*:\s*([^\n]*?)\s*$/);
 if(!m) return;
 var k = m[1].toLowerCase(), v = m[2];
 if(k==='user-agent' || k==='useragent'){
 if(!cur || inRules){ cur = {agents:[], rules:[]}; groups.push(cur); inRules = false; }
 cur.agents.push(v.trim());
 } else if(k==='allow' || k==='disallow'){
 if(!cur) return;
 inRules = true;
 cur.rules.push({type:k, path:v.trim()});
 }
 });
 return groups;
 }
 function uaToken(ua){
 ua = ua.trim();
 if(ua==='*') return '*';
 var m = ua.match(/^[A-Za-z_\-]+/);
 return m ? m[0].toLowerCase() : null;
 }
 function productToken(botName){ return botName.split(' ')[0]; } // 'GPTBot (training)' -> 'GPTBot'
 function matchGroup(groups, botName){
 var product = productToken(botName).toLowerCase();
 function pick(tok){
 var gs = groups.filter(function(g){ return g.agents.some(function(a){ return uaToken(a)===tok; }); });
 if(!gs.length) return null;
 var agents = [];
 gs.forEach(function(g){ g.agents.forEach(function(a){ if(uaToken(a)===tok && agents.indexOf(a)<0) agents.push(a); }); });
 return {source: tok==='*' ? 'star' : 'named', ua: agents.join(', '), rules: [].concat.apply([], gs.map(function(g){ return g.rules; }))};
 }
 return pick(product) || pick('*');
 }
 function patToRe(p){
 var end = p.charAt(p.length-1)==='$';
 if(end) p = p.slice(0,-1);
 var rx = Array.prototype.map.call(p, function(c){ return c==='*' ? '.*' : c.replace(/[.*+?^${}()|[\]\\\/]/g,'\\$&'); }).join('');
 return new RegExp('^' + rx + (end ? '$' : ''));
 }
 function isAllowed(rules, path){
 var best = null; // [length, isAllow]
 rules.forEach(function(r){
 if(r.path==='') return; // empty value = no rule
 if(!patToRe(r.path).test(path)) return;
 var cand = [Array.from(r.path).length, r.type==='allow'];
 if(!best || cand[0] > best[0] || (cand[0]===best[0] && cand[1] && !best[1])) best = cand;
 });
 return best ? best[1] : true;
 }
 function rootAllowed(group){
 if(!group) return {status:'unknown', root:true, detail:'No matching User-agent group (and no *). Many crawlers treat that as allow.'};
 var effDis = group.rules.filter(function(r){ return r.type==='disallow' && r.path!==''; });
 var effAllow = group.rules.filter(function(r){ return r.type==='allow' && r.path!==''; });
 var root = isAllowed(group.rules, '/');
 if(!effDis.length) return {status:'allowed', root:root, detail:'No blanket Disallow: / for this group — root looks crawlable.'};
 if(!root && !effAllow.length) return {status:'blocked', root:root, detail:'Group matches and Disallow: / (or /*) applies to the site root.'};
 return {status:'partial', root:root, detail:'Some Disallow rules exist — check paths carefully. Root may still be allowed.'};
 }
 function verdictFor(text, botName){
 var g = matchGroup(parseRobots(capBytes(text)), botName);
 var r = rootAllowed(g);
 return {status:r.status, root:r.root, source:g ? g.source : 'none', ua:g ? g.ua : null};
 }
 function esc(s){ return String(s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
 function render(text, sourceLabel){
 var groups = parseRobots(capBytes(text));
 var html = '<p class="fine">Source: '+esc(sourceLabel)+'</p><ul class="bot-results">';
 BOTS.forEach(function(b){
 var g = matchGroup(groups, b.name);
 var r = rootAllowed(g);
 var detail = r.status==='partial' ? (r.root ? "The homepage is allowed, but some Disallow rules apply, so check the file for the paths affected." : "The homepage is disallowed, but some paths are allowed, so check the file for which ones.") : r.detail;
 html += '<li class="bot-'+r.status+'" data-root="'+(r.root?'allowed':'blocked')+'"><strong>'+b.name+'</strong>: '+r.status.toUpperCase()+
 '<br><span class="fine">'+(g?('User-agent group: '+esc(g.ua)+' — '):'')+detail+(b.note?' '+b.note:'')+'</span></li>';
 });
 html += '</ul><p class="fine">This is a static client-side check for humans — not a guarantee of crawl behaviour. Prefer allowing search crawlers (Googlebot, Bingbot, OAI-SearchBot, PerplexityBot, Claude-SearchBot) for search visibility. Training and user-triggered bots are separate policy choices; user-triggered fetches may ignore robots.txt.</p>';
 out.innerHTML = html;
 }
 function normaliseSiteUrl(raw){
 var s = String(raw == null ? '' : raw).trim();
 if(!s) return { ok:false, reason:'empty' };
 // protocol-relative //example.com
 if(/^\/\//.test(s)) s = 'https:' + s;
 if(!/^[a-z][a-z0-9+.-]*:/i.test(s)) s = 'https://' + s;
 try {
 var u = new URL(s);
 if(u.protocol !== 'http:' && u.protocol !== 'https:') return { ok:false, reason:'scheme' };
 if(!u.hostname) return { ok:false, reason:'host' };
 return { ok:true, url:u, href:u.toString() };
 } catch(err){
 return { ok:false, reason:'parse' };
 }
 }
 function applyUrlField(){
 var el = form.elements.url;
 var raw = (el.value || '').trim();
 if(!raw) return;
 var n = normaliseSiteUrl(raw);
 if(n.ok) el.value = n.href;
 }
 if(typeof module !== 'undefined' && module.exports) module.exports = {BOTS:BOTS, MAX_BYTES:MAX_BYTES, capBytes:capBytes, parseRobots:parseRobots, matchGroup:matchGroup, isAllowed:isAllowed, rootAllowed:rootAllowed, verdictFor:verdictFor};
 if(!form || !out) return;
 form.elements.url.addEventListener('blur', applyUrlField);
 function say(msg){ out.textContent = ''; var p = document.createElement('p'); p.className = 'fine'; p.textContent = msg; out.appendChild(p); }
// Fetched robots.txt is shown with textContent only (never innerHTML).
function showFetched(text){
 var d = document.createElement('details'); d.className = 'fetched-robots';
 var s = document.createElement('summary'); s.textContent = 'Show the robots.txt we fetched';
 var pre = document.createElement('pre'); pre.className = 'example-pre'; pre.style.maxHeight = '24rem'; pre.textContent = text;
 d.appendChild(s); d.appendChild(pre); out.appendChild(d);
}
form.addEventListener('submit', function(e){
 e.preventDefault();
 var paste = (form.elements.paste.value||'').trim();
 if(paste){ render(paste, 'pasted text'); return; }
 applyUrlField();
 var raw = (form.elements.url.value||'').trim();
 if(!raw){ say('Enter a site (e.g. trendibizz.com) or paste robots.txt.'); return; }
 var n = normaliseSiteUrl(raw);
 if(!n.ok){ say('Enter a site or URL (e.g. trendibizz.com). https:// is added if you leave it off.'); return; }
 var host = n.url.hostname;
 var aiBox = null, aiTimer = null;
 if(window.TrendiUI && typeof window.TrendiUI.aiStatus === 'function'){
   out.textContent = '';
   var statusHost = document.createElement('div');
   out.appendChild(statusHost);
   aiBox = window.TrendiUI.aiStatus(statusHost).thinking([
     'Connecting to ' + host,
     'Fetching /robots.txt',
     'Evaluating RFC 9309 bot rules'
   ]);
   aiTimer = setTimeout(function(){ if(aiBox) aiBox.step(0, 'done'); }, 350);
 } else {
   say('Fetching https://' + host + '/robots.txt…');
 }
 // Same-origin endpoint: Trendi's server fetches only https://<host>/robots.txt (CSP connect-src stays 'self').
 fetch('/api/robots?url=' + encodeURIComponent(host), {method:'GET', credentials:'same-origin', headers:{accept:'text/plain'}})
 .then(function(res){
 if(aiBox) aiBox.step(1, 'done');
 var ct = res.headers.get('content-type') || '';
 if(res.ok && /^text\/plain/i.test(ct)) return res.text().then(function(t){ return {ok:true, text:t, source:res.headers.get('x-trendi-source') || ('https://' + host + '/robots.txt'), truncated:res.headers.get('x-trendi-truncated') === '1'}; });
 return res.json().catch(function(){ return {}; }).then(function(j){ return {ok:false, error:j.error || ('http_' + res.status), message:j.message}; });
 })
 .then(function(r){
 if(aiTimer) clearTimeout(aiTimer);
 if(aiBox) aiBox.done();
 if(!r.ok){
 if(r.error === 'not_found'){ say(r.message || 'No robots.txt found at that site. Under RFC 9309 that means crawlers may fetch everything.'); return; }
 say((r.message || 'We could not fetch that robots.txt.') + ' You can open the file yourself and paste it below.'); return;
 }
 render(r.text, r.source + (r.truncated ? ' (first 512 KB)' : ''));
 showFetched(r.text);
 })
 .catch(function(){ if(aiTimer) clearTimeout(aiTimer); if(aiBox) aiBox.done(); say('Could not reach the checker. Open the robots.txt yourself and paste it below.'); });
});
})();
