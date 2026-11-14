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

/** A still title card, drawn with the showcase template, used when a video has no photo. */
async function titleCard(brand, text, [W, H]) {
  const element = showcase(brand, [], text, [W, H]);
  const svg = await satori(element, { width: W, height: H, fonts: FONTS });
  return new Resvg(svg, { fitTo: { mode: 'width', value: W } }).render().asPng();
}

async function renderVideo(body) {
  const [W, H] = FORMATS[body.format] || FORMATS.portrait;
  const photos = (body.photos || []).map(dataUri).filter(Boolean).slice(0, 20);
  const headline = String((body.text || {}).headline || '').trim();
  // A video does not need a photo: with none we animate a title card of the brand and the
  // headline, so "type a line and press Generate" is a complete instruction.
  if (!photos.length && !headline) {
    throw Object.assign(new Error('Add a headline, or a photo, and try again'), { status: 400 });
  }
  const clip = 3, transition = 0.5, cardSeconds = 6;
  const total = photos.length ? photos.length * clip - (photos.length - 1) * transition : cardSeconds;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'concierge-video-'));
  try {
    const files = photos.map((photo, i) => {
      const file = path.join(dir, `${i}.jpg`);
      decodePhoto(photo, file);
      return file;
    });
    const titleFile = path.join(dir, 'title.txt');
    fs.writeFileSync(titleFile, headline.replace(/[\r\n]+/g, ' '));
    const music = body.music ? audioFile(body.music, dir) : '';
    const args = [];
    if (!files.length) {
      // No photo: one title card, slowly zoomed so it reads as motion rather than a still.
      const card = path.join(dir, 'card.png');
      fs.writeFileSync(card, await titleCard(body.brand || {}, body.text || {}, [W, H]));
      files.push(card);
      args.push('-loop', '1', '-t', String(cardSeconds), '-i', card);
    } else {
      files.forEach((file) => args.push('-loop', '1', '-t', String(clip), '-i', file));
    }
    if (music) args.push('-i', music);

    const parts = files.map((_, i) => `[${i}:v]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},setsar=1,format=yuv420p[v${i}]`);
    let last = 'v0';
    if (!photos.length) {
      // 6 seconds of gentle zoom on the card; the headline is already drawn into it.
      parts.length = 0;
      parts.push(`[0:v]scale=${W * 2}:${H * 2},zoompan=z='min(zoom+0.0006,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=${cardSeconds * 30}:s=${W}x${H}:fps=30,setsar=1,format=yuv420p[vout]`);
    } else {
      for (let i = 1; i < files.length; i++) {
        const offset = (i * (clip - transition)).toFixed(2);
        parts.push(`[${last}][v${i}]xfade=transition=fade:duration=${transition}:offset=${offset}[x${i}]`);
        last = `x${i}`;
      }
      parts.push(`[${last}]drawtext=fontfile=${FONT_BOLD}:textfile=${titleFile}:fontcolor=white:fontsize=${Math.round(W / 16)}:borderw=4:bordercolor=black@0.55:x=(w-text_w)/2:y=h-(text_h*2.2)[vout]`);
    }
    if (music) {
      // The music input follows the video inputs, however many there were.
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

/* Camera moves, one per shot. Slow enough to read as footage rather than a slideshow. */
const MOVES = [
  "zoompan=z='min(zoom+0.0009,1.18)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
  "zoompan=z='if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0009))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
  "zoompan=z='min(zoom+0.0009,1.18)':x='0':y='ih/2-(ih/zoom/2)'",
  "zoompan=z='min(zoom+0.0009,1.18)':x='iw-iw/zoom':y='ih/2-(ih/zoom/2)'",
];

/**
 * A video the AI actually makes: several frames generated from the prompt, then moved with real
 * camera motion and cross-faded. Cloudflare's catalogue on this account has no text-to-video
 * model (checked 2026-11-14: Text-to-Image x10, no video task), so the footage is AI frames
 * animated here rather than a still card with a headline on it.
 */
async function renderAiVideo(body) {
  const [W, H] = FORMATS[body.format] || FORMATS.portrait;
  const prompt = String(body.prompt || '').trim();
  if (prompt.length < 3) throw Object.assign(new Error('Describe the video you want'), { status: 400 });
  const shots = Math.min(Math.max(1, Number(body.shots) || 4), 6);
  const per = 3, transition = 0.6;
  const total = shots * per - (shots - 1) * transition;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'concierge-aivideo-'));
  try {
    // Different angle per shot so it reads as a sequence, not the same picture four times.
    const angles = ['wide establishing shot', 'close-up detail', 'medium shot from a low angle', 'overhead view', 'slow dolly forward', 'backlit golden-hour shot'];
    const frames = await Promise.all(Array.from({ length: shots }, (_, i) =>
      cloudflareImage(`${prompt}. ${angles[i % angles.length]}. Cinematic, photorealistic, vertical 4:5 composition.`)));
    const files = frames.map((buffer, i) => {
      const file = path.join(dir, `f${i}.jpg`);
      fs.writeFileSync(file, buffer);
      return file;
    });
    const brandName = String((body.brand || {}).name || '').replace(/[:'\\]/g, ' ');
    const args = [];
    files.forEach((file) => args.push('-loop', '1', '-t', String(per), '-i', file));
    const music = body.music ? audioFile(body.music, dir) : '';
    if (music) args.push('-i', music);

    const parts = files.map((_, i) =>
      `[${i}:v]scale=${W * 2}:${H * 2}:force_original_aspect_ratio=increase,crop=${W * 2}:${H * 2},${MOVES[i % MOVES.length]}:d=${per * 30}:s=${W}x${H}:fps=30,setsar=1,format=yuv420p[v${i}]`);
    let last = 'v0';
    for (let i = 1; i < files.length; i++) {
      const offset = (i * (per - transition)).toFixed(2);
      parts.push(`[${last}][v${i}]xfade=transition=fade:duration=${transition}:offset=${offset}[x${i}]`);
      last = `x${i}`;
    }
    if (brandName.trim()) {
      parts.push(`[${last}]drawtext=fontfile=${FONT_BOLD}:text='${brandName.trim()}':fontcolor=white@0.92:fontsize=${Math.round(W / 26)}:borderw=3:bordercolor=black@0.5:x=${Math.round(W / 22)}:y=h-${Math.round(H / 14)}[vout]`);
    } else {
      parts.push(`[${last}]null[vout]`);
    }
    if (music) {
      parts.push(`[${files.length}:a]aloop=loop=-1:size=2e9,atrim=0:${total},volume=0.35,afade=t=out:st=${(total - 1).toFixed(2)}:d=1[a]`);
    }
    args.push('-filter_complex', parts.join(';'), '-map', '[vout]');
    if (music) args.push('-map', '[a]', '-shortest'); else args.push('-an');
    const out = path.join(dir, 'out.mp4');
    args.push('-t', String(total), '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
      '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out);
    await run('ffmpeg', ['-y', ...args], { timeout: 300000 });
    return fs.readFileSync(out);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
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
      if (req.url === '/render/ai-video') return send(res, 200, 'video/mp4', await renderAiVideo(body));
      if (req.url === '/ai-image') return send(res, 200, 'image/jpeg', await aiImage(body));
      return send(res, 404, 'application/json', Buffer.from('{"detail":"not found"}'));
    } catch (error) {
      console.error(error);
      return send(res, error.status || 500, 'application/json', Buffer.from(JSON.stringify({ detail: String(error.message || error) })));
    }
  });
});
server.listen(PORT, '0.0.0.0', () => console.log(`media-render on ${PORT}`));
