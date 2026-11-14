/* Concierge media renderer: Satori images and Cloudflare AI images. It does not make video. */
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const satoriModule = require('satori');
const satori = satoriModule.default || satoriModule;
const React = require('react');
const { Resvg } = require('@resvg/resvg-js');
const h = React.createElement;

const PORT = Number(process.env.PORT || 8099);
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID || '';
// Scoped API token only: the account's global API key was retired 2026-11-12.
const CF_TOKEN = process.env.CF_API_TOKEN || '';
const FONT_REG = process.env.FONT_REGULAR || '/usr/share/fonts/dejavu/DejaVuSans.ttf';
const FONT_BOLD = process.env.FONT_BOLD || '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf';
const FONTS = [
  { name: 'DejaVu', data: fs.readFileSync(FONT_REG), weight: 400, style: 'normal' },
  { name: 'DejaVu', data: fs.readFileSync(FONT_BOLD), weight: 700, style: 'normal' },
];

const FORMATS = {
  square: [1080, 1080],
  portrait: [1080, 1350],
  story: [1080, 1920],
};

function dataUri(value) {
  return typeof value === 'string' && value.startsWith('data:image/') ? value : '';
}

function logo(brand) {
  if (brand.logo && dataUri(brand.logo)) return h('img', { src: brand.logo, style: { height: 92, width: 'auto' } });
  return h('div', { style: { fontSize: 42, fontWeight: 700, color: '#ffffff' } }, brand.name || '');
}

function accentTint(brand, amount) {
  // Mix the business's accent into the dark canvas, so a poster without a photo still looks
  // designed rather than like a rendering failure (which is exactly how it was reported).
  const accent = (brand.accent || '#c8f560').replace('#', '');
  const r = parseInt(accent.slice(0, 2), 16) || 200;
  const g = parseInt(accent.slice(2, 4), 16) || 245;
  const b = parseInt(accent.slice(4, 6), 16) || 96;
  return `rgba(${r}, ${g}, ${b}, ${amount})`;
}

function showcase(brand, photos, text, [W, H]) {
  const photo = photos[0];
  const accent = brand.accent || '#c8f560';
  // Without a photo this is a colour field with big type in the middle: a finished-looking poster
  // instead of a black rectangle with a headline at the bottom.
  const fallback = photo ? null : h('div', {
    style: {
      position: 'absolute', width: W, height: H, display: 'flex',
      backgroundImage: `radial-gradient(120% 90% at 15% 0%, ${accentTint(brand, 0.55)} 0%, rgba(17,17,17,0) 62%), radial-gradient(110% 80% at 90% 100%, ${accentTint(brand, 0.38)} 0%, rgba(17,17,17,0) 58%)`,
      backgroundColor: '#141518',
    },
  });
  return h('div', { style: { display: 'flex', width: W, height: H, position: 'relative', backgroundColor: '#141518' } },
    fallback,
    photo ? h('img', { src: photo, style: { position: 'absolute', width: W, height: H, objectFit: 'cover' } }) : null,
    photo ? h('div', { style: { position: 'absolute', width: W, height: H, backgroundImage: 'linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.86))' } }) : null,
    h('div', { style: { position: 'absolute', top: 64, left: 64, right: 64, display: 'flex', alignItems: 'center' } }, logo(brand)),
    h('div', {
      style: photo
        ? { position: 'absolute', left: 64, right: 64, bottom: 96, display: 'flex', flexDirection: 'column' }
        : { position: 'absolute', left: 72, right: 72, top: 0, bottom: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center' },
    },
      h('div', { style: { fontSize: photo ? 68 : 84, fontWeight: 700, color: '#ffffff', lineHeight: 1.04, letterSpacing: '-0.02em' } }, text.headline || ''),
      text.subline ? h('div', { style: { fontSize: photo ? 34 : 38, color: '#e9edf2', marginTop: 22, lineHeight: 1.3 } }, text.subline) : null,
      h('div', { style: { width: 180, height: 12, backgroundColor: accent, marginTop: 30 } })),
    brand.contact ? h('div', { style: { position: 'absolute', right: 64, bottom: 40, fontSize: 24, color: '#cfd6de' } }, brand.contact) : null,
  );
}

function beforeAfter(brand, photos, text, [W, H]) {
  const half = Math.floor((W - 24) / 2);
  return h('div', { style: { display: 'flex', width: W, height: H, backgroundColor: '#0d0f12', flexDirection: 'column' } },
    h('div', { style: { display: 'flex', flexDirection: 'column', padding: 56, flexGrow: 0 } },
      h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between' } }, logo(brand),
        h('div', { style: { fontSize: 26, color: '#c8f560', fontWeight: 700 } }, text.kicker || 'BEFORE / AFTER')),
      h('div', { style: { fontSize: 62, fontWeight: 700, color: '#ffffff', marginTop: 28, lineHeight: 1.08 } }, text.headline || '')),
    h('div', { style: { display: 'flex', flexDirection: 'row', gap: 24, paddingLeft: 56, paddingRight: 56 } },
      [0, 1].map((i) => h('div', { key: String(i), style: { display: 'flex', flexDirection: 'column', width: half } },
        h('div', { style: { position: 'relative', width: half, height: 700, display: 'flex' } },
          photos[i] ? h('img', { src: photos[i], style: { width: half, height: 700, objectFit: 'cover' } }) : null,
          h('div', { style: { position: 'absolute', top: 20, left: 20, padding: '10px 18px', backgroundColor: i === 0 ? '#1a1d21' : (brand.accent || '#c8f560'), fontSize: 24, fontWeight: 700, color: i === 0 ? '#ffffff' : '#101408' } }, i === 0 ? (text.before_label || 'BEFORE') : (text.after_label || 'AFTER'))),
        h('div', { style: { fontSize: 28, color: '#aeb7c2', marginTop: 16 } }, i === 0 ? (text.before_caption || '') : (text.after_caption || ''))
      ))),
    h('div', { style: { display: 'flex', justifyContent: 'space-between', padding: '36px 56px' } },
      h('div', { style: { fontSize: 26, color: '#cfd6de' } }, brand.contact || ''),
      h('div', { style: { width: 120, height: 10, backgroundColor: brand.accent || '#c8f560' } })),
  );
}

function quote(brand, photos, text, [W, H]) {
  return h('div', { style: { display: 'flex', width: W, height: H, backgroundColor: brand.accent || '#c8f560', flexDirection: 'column', justifyContent: 'space-between', padding: 72 } },
    logo(brand),
    h('div', { style: { display: 'flex', flexDirection: 'column' } },
      h('div', { style: { fontSize: 76, fontWeight: 700, color: '#101408', lineHeight: 1.08 } }, text.headline || ''),
      text.subline ? h('div', { style: { fontSize: 36, color: '#1b2110', marginTop: 26, lineHeight: 1.3 } }, text.subline) : null),
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' } },
      h('div', { style: { fontSize: 26, color: '#1b2110' } }, brand.contact || ''),
      h('div', { style: { fontSize: 24, color: '#1b2110', fontWeight: 700 } }, brand.name || '')),
  );
}

function service(brand, photos, text, [W, H]) {
  const lines = (text.subline || '').split('\n').filter(Boolean).slice(0, 4);
  return h('div', { style: { display: 'flex', width: W, height: H, backgroundColor: '#0d0f12', flexDirection: 'column', justifyContent: 'space-between', padding: 72 } },
    logo(brand),
    h('div', { style: { display: 'flex', flexDirection: 'column' } },
      h('div', { style: { fontSize: 74, fontWeight: 700, color: '#ffffff', lineHeight: 1.06 } }, text.headline || ''),
      h('div', { style: { display: 'flex', flexDirection: 'column', marginTop: 34 } },
        lines.map((line, i) => h('div', { key: String(i), style: { display: 'flex', alignItems: 'center', marginTop: 14 } },
          h('div', { style: { width: 14, height: 14, backgroundColor: brand.accent || '#c8f560', marginRight: 18 } }),
          h('div', { style: { fontSize: 34, color: '#dfe6ee' } }, line))))),
    h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' } },
      h('div', { style: { fontSize: 26, color: '#aeb7c2' } }, brand.contact || ''),
      h('div', { style: { width: 140, height: 10, backgroundColor: brand.accent || '#c8f560' } })),
  );
}

const TEMPLATES = { showcase, before_after: beforeAfter, quote, service };

async function renderImage(body) {
  const [W, H] = FORMATS[body.format] || FORMATS.square;
  const template = TEMPLATES[body.template];
  if (!template) throw Object.assign(new Error('Unknown template'), { status: 400 });
  const brand = body.brand || {};
  const photos = (body.photos || []).map(dataUri).filter(Boolean).slice(0, 20);
  const element = template(brand, photos, body.text || {}, [W, H]);
  const svg = await satori(element, { width: W, height: H, fonts: FONTS });
  return new Resvg(svg, { fitTo: { mode: 'width', value: W } }).render().asPng();
}

async function cloudflareImage(prompt) {
  if (!CF_ACCOUNT || !CF_TOKEN) throw Object.assign(new Error('AI images are not configured'), { status: 503 });
  const response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/ai/run/@cf/black-forest-labs/flux-1-schnell`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${CF_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: String(prompt || '').slice(0, 2000), steps: 4 }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.result || !data.result.image) {
    throw Object.assign(new Error(`AI image failed (${response.status})`), { status: 502 });
  }
  return Buffer.from(data.result.image, 'base64');
}

async function aiImage(body) {
  return cloudflareImage(body.prompt);
}


function send(res, status, type, body) {
  res.writeHead(status, { 'Content-Type': type, 'Content-Length': body.length, 'Cache-Control': 'no-store' });
  res.end(body);
}

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/health') return send(res, 200, 'application/json', Buffer.from('{"ok":true}'));
  if (req.method !== 'POST') return send(res, 404, 'application/json', Buffer.from('{"detail":"not found"}'));
  let size = 0;
  const chunks = [];
  req.on('data', (chunk) => {
    size += chunk.length;
    if (size > 100 * 1024 * 1024) { req.destroy(); return; }
    chunks.push(chunk);
  });
  req.on('end', async () => {
    try {
      const body = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
      if (req.url === '/render/image') return send(res, 200, 'image/png', await renderImage(body));
      if (req.url === '/ai-image') return send(res, 200, 'image/jpeg', await aiImage(body));
      return send(res, 404, 'application/json', Buffer.from('{"detail":"not found"}'));
    } catch (error) {
      console.error(error);
      return send(res, error.status || 500, 'application/json', Buffer.from(JSON.stringify({ detail: String(error.message || error) })));
    }
  });
});
server.listen(PORT, '0.0.0.0', () => console.log(`media-render on ${PORT}`));
