/* Concierge media renderer: Satori images, FFmpeg slideshows, Cloudflare AI images. */
'use strict';
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFile } = require('child_process');
const satoriModule = require('satori');
const satori = satoriModule.default || satoriModule;
const React = require('react');
const { Resvg } = require('@resvg/resvg-js');
const h = React.createElement;

const PORT = Number(process.env.PORT || 8099);
const CF_ACCOUNT = process.env.CF_ACCOUNT_ID || '';
const CF_KEY = process.env.CF_API_KEY || '';
const CF_EMAIL = process.env.CF_EMAIL || '';
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

function showcase(brand, photos, text, [W, H]) {
  const photo = photos[0];
  return h('div', { style: { display: 'flex', width: W, height: H, position: 'relative', backgroundColor: '#111111' } },
    photo ? h('img', { src: photo, style: { position: 'absolute', width: W, height: H, objectFit: 'cover' } }) : null,
    h('div', { style: { position: 'absolute', width: W, height: H, backgroundImage: 'linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.86))' } }),
    h('div', { style: { position: 'absolute', top: 64, left: 64, right: 64, display: 'flex', alignItems: 'center' } }, logo(brand)),
    h('div', { style: { position: 'absolute', left: 64, right: 64, bottom: 96, display: 'flex', flexDirection: 'column' } },
      h('div', { style: { fontSize: 68, fontWeight: 700, color: '#ffffff', lineHeight: 1.06 } }, text.headline || ''),
      text.subline ? h('div', { style: { fontSize: 34, color: '#e9edf2', marginTop: 20, lineHeight: 1.3 } }, text.subline) : null,
      h('div', { style: { width: 180, height: 12, backgroundColor: brand.accent || '#c8f560', marginTop: 28 } })),
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

function decodePhoto(value, file) {
  const match = /^data:image\/[a-z0-9.+-]+;base64,(.*)$/i.exec(value || '');
  if (!match) throw Object.assign(new Error('Photos must be image data URIs'), { status: 400 });
  fs.writeFileSync(file, Buffer.from(match[1], 'base64'));
}

function run(command, args, options) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { ...options, maxBuffer: 8 << 20 }, (error, stdout, stderr) => {
      if (error) reject(new Error((stderr || error.message).slice(-600)));
      else resolve(stdout);
    });
  });
}

function audioFile(value, dir) {
  const match = /^data:audio\/([a-z0-9.+-]+);base64,(.*)$/i.exec(value || '');
  if (!match) throw Object.assign(new Error('Music must be an audio upload'), { status: 400 });
  const ext = { mpeg: 'mp3', 'mp3': 'mp3', mp4: 'm4a', 'x-m4a': 'm4a', wav: 'wav', 'x-wav': 'wav', ogg: 'ogg', webm: 'webm' }[match[1].toLowerCase()] || 'mp3';
  const file = path.join(dir, `music.${ext}`);
  fs.writeFileSync(file, Buffer.from(match[2], 'base64'));
  return file;
}

async function renderVideo(body) {
  const [W, H] = FORMATS[body.format] || FORMATS.portrait;
  const photos = (body.photos || []).map(dataUri).filter(Boolean).slice(0, 20);
  if (!photos.length) throw Object.assign(new Error('At least one photo is required'), { status: 400 });
  const clip = 3, transition = 0.5;
  const total = photos.length * clip - (photos.length - 1) * transition;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'concierge-video-'));
  try {
    const files = photos.map((photo, i) => {
      const file = path.join(dir, `${i}.jpg`);
      decodePhoto(photo, file);
      return file;
    });
    const titleFile = path.join(dir, 'title.txt');
    fs.writeFileSync(titleFile, String((body.text || {}).headline || '').replace(/[\r\n]+/g, ' '));
    const music = body.music ? audioFile(body.music, dir) : '';
    const args = [];
    files.forEach((file) => args.push('-loop', '1', '-t', String(clip), '-i', file));
    if (music) args.push('-i', music);

    const parts = files.map((_, i) => `[${i}:v]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},setsar=1,format=yuv420p[v${i}]`);
    let last = 'v0';
    for (let i = 1; i < files.length; i++) {
      const offset = (i * (clip - transition)).toFixed(2);
      parts.push(`[${last}][v${i}]xfade=transition=fade:duration=${transition}:offset=${offset}[x${i}]`);
      last = `x${i}`;
    }
    parts.push(`[${last}]drawtext=fontfile=${FONT_BOLD}:textfile=${titleFile}:fontcolor=white:fontsize=${Math.round(W / 16)}:borderw=4:bordercolor=black@0.55:x=(w-text_w)/2:y=h-(text_h*2.2)[vout]`);
    if (music) {
      parts.push(`[${files.length}:a]aloop=loop=-1:size=2e9,atrim=0:${total},volume=0.35,afade=t=out:st=${(total - 1).toFixed(2)}:d=1[a]`);
    }
    args.push('-filter_complex', parts.join(';'), '-map', '[vout]');
    if (music) args.push('-map', '[a]', '-shortest');
    else args.push('-an');
    const out = path.join(dir, 'out.mp4');
    args.push('-t', String(total), '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out);
    await run('ffmpeg', ['-y', ...args], { timeout: 240000 });
    return fs.readFileSync(out);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

async function aiImage(body) {
  if (!CF_ACCOUNT || !CF_KEY) throw Object.assign(new Error('AI images are not configured'), { status: 503 });
  const response = await fetch(`https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT}/ai/run/@cf/black-forest-labs/flux-1-schnell`, {
    method: 'POST',
    headers: { 'X-Auth-Email': CF_EMAIL, 'X-Auth-Key': CF_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt: String(body.prompt || '').slice(0, 2000), steps: 4 }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.result || !data.result.image) {
    throw Object.assign(new Error(`AI image failed (${response.status})`), { status: 502 });
  }
  return Buffer.from(data.result.image, 'base64');
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
      if (req.url === '/render/video') return send(res, 200, 'video/mp4', await renderVideo(body));
      if (req.url === '/ai-image') return send(res, 200, 'image/jpeg', await aiImage(body));
      return send(res, 404, 'application/json', Buffer.from('{"detail":"not found"}'));
    } catch (error) {
      console.error(error);
      return send(res, error.status || 500, 'application/json', Buffer.from(JSON.stringify({ detail: String(error.message || error) })));
    }
  });
});
server.listen(PORT, '0.0.0.0', () => console.log(`media-render on ${PORT}`));
