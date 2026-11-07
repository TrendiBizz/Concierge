// Imports the pictures from a WordPress website's media library into SocialSync's photo library.
// Safe to run again: pictures that are already in the library (same file name) are skipped.
//
// Usage (server must be running):
//   node tools/import-site.mjs
//   node tools/import-site.mjs --site https://pukekoconstruction.co.nz --server http://127.0.0.1:4377
//   node tools/import-site.mjs --dry-run        (show what would be imported)
//
// The passcode is read from SOCIALSYNC_PASSCODE, --passcode, or server/data/config.json.

import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const run = promisify(execFile);
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const SITE = arg('--site', 'https://pukekoconstruction.co.nz').replace(/\/+$/, '');
const SERVER = arg('--server', 'http://127.0.0.1:4377').replace(/\/+$/, '');
const DRY = process.argv.includes('--dry-run');
const MAX_BYTES = 45 * 1024 * 1024;
const KEEP_DIR = path.join(root, 'import', 'site', 'images');
const UA = 'Mozilla/5.0 (Macintosh) SocialSyncImporter';

function passcode() {
  const given = arg('--passcode', process.env.SOCIALSYNC_PASSCODE);
  if (given) return given;
  for (const file of [path.join(root, 'data', 'config.json'), path.join(root, 'server', 'data', 'config.json')]) {
    if (existsSync(file)) return JSON.parse(readFileSync(file, 'utf8')).passcode;
  }
  throw new Error('No passcode found. Pass --passcode or start the server once first.');
}

const EXT_BY_MIME = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
  'image/gif': 'gif',
  'image/avif': 'avif',
};

const MIME_BY_EXT = { jpg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif' };

function humanise(text) {
  return text.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^./, (c) => c.toUpperCase());
}

// Decides what to do with one WordPress media item. Returns null to ignore it silently.
function plan(item) {
  const mime = item.mime_type || '';
  if (!mime.startsWith('image/') || !EXT_BY_MIME[mime]) return null;
  const url = item.source_url;
  const stem = decodeURIComponent(url.split('/').pop()).replace(/\.[^.]+$/, '');
  const width = (item.media_details && item.media_details.width) || 0;

  if (/placeholder|favico/i.test(stem)) return { skip: 'placeholder or icon', stem };
  const isLogo = /logo/i.test(stem) || /^pukeko$/i.test(stem);
  if (!isLogo && width < 400) return { skip: 'too small', stem };

  const randomName = stem.length > 40;
  const projectMatch = /^project[-_ ]?(\d+)$/i.exec(stem);
  let project = 'Pukeko website gallery';
  let caption = (item.alt_text || '').trim() || (randomName ? `Website photo ${item.id}` : humanise(stem));
  if (isLogo) {
    project = 'Pukeko brand';
    caption = 'Logo';
  } else if (projectMatch) {
    project = 'Pukeko projects (website)';
    caption = (item.alt_text || '').trim() || `Project ${projectMatch[1]}`;
  } else if (/engineering|drafting|draughting|building-works/i.test(stem)) {
    project = 'Pukeko services (website)';
  }

  const ext = EXT_BY_MIME[mime] === 'avif' ? 'jpg' : EXT_BY_MIME[mime];
  const name = randomName ? `website-${item.id}` : stem;
  return {
    url,
    mime,
    ext,
    filename: `${name}.${ext}`,
    needsConvert: mime === 'image/avif',
    project,
    caption,
    stem,
  };
}

async function listSiteMedia() {
  const all = [];
  for (let page = 1; page < 20; page += 1) {
    const res = await fetch(
      `${SITE}/wp-json/wp/v2/media?per_page=100&page=${page}&_fields=id,source_url,alt_text,mime_type,media_details`,
      { headers: { 'User-Agent': UA } },
    );
    if (!res.ok) {
      if (page === 1) throw new Error(`Could not read ${SITE}/wp-json/wp/v2/media (HTTP ${res.status}).`);
      break;
    }
    const batch = await res.json();
    all.push(...batch);
    if (batch.length < 100) break;
  }
  return all;
}

async function download(url) {
  const res = await fetch(url, { headers: { 'User-Agent': UA } });
  if (!res.ok) throw new Error(`download failed (HTTP ${res.status})`);
  const buffer = Buffer.from(await res.arrayBuffer());
  if (buffer.length > MAX_BYTES) throw new Error('file is larger than 45 MB');
  return buffer;
}

// macOS can decode AVIF through sips; the server only stores JPEG, PNG, GIF, WebP, HEIC, MP4, MOV.
async function avifToJpeg(buffer) {
  const input = path.join(tmpdir(), `socialsync-${process.pid}-${Date.now()}.avif`);
  const output = input.replace(/\.avif$/, '.jpg');
  writeFileSync(input, buffer);
  try {
    await run('/usr/bin/sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '90', input, '--out', output]);
    return readFileSync(output);
  } finally {
    rmSync(input, { force: true });
    rmSync(output, { force: true });
  }
}

async function main() {
  console.log(`Reading the media library of ${SITE} ...`);
  const items = await listSiteMedia();
  const plans = items.map(plan).filter(Boolean);
  const wanted = plans.filter((p) => !p.skip);
  const skipped = plans.filter((p) => p.skip);
  console.log(`${items.length} items on the site: ${wanted.length} to import, ${skipped.length} skipped.`);
  for (const s of skipped) console.log(`  skip  ${s.stem} (${s.skip})`);

  if (DRY) {
    for (const p of wanted) console.log(`  would import ${p.filename}  [${p.project}] "${p.caption}"`);
    return;
  }

  const login = await fetch(`${SERVER}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ passcode: passcode() }),
  });
  if (!login.ok) throw new Error(`Sign-in to ${SERVER} failed (HTTP ${login.status}). Is the server running?`);
  const { token } = await login.json();
  const auth = { Authorization: `Bearer ${token}` };

  const existing = new Set(
    ((await (await fetch(`${SERVER}/api/media`, { headers: auth })).json()).media || []).map((m) => m.filename),
  );

  mkdirSync(KEEP_DIR, { recursive: true });
  let imported = 0;
  let already = 0;
  const failed = [];

  for (const p of wanted) {
    if (existing.has(p.filename)) {
      already += 1;
      continue;
    }
    try {
      let data = await download(p.url);
      if (p.needsConvert) data = await avifToJpeg(data);
      writeFileSync(path.join(KEEP_DIR, p.filename), data); // keep a local copy of what was imported
      const query = new URLSearchParams({ filename: p.filename, project: p.project, caption: p.caption });
      const res = await fetch(`${SERVER}/api/media?${query}`, {
        method: 'POST',
        headers: { ...auth, 'Content-Type': MIME_BY_EXT[p.ext] },
        body: data,
      });
      if (!res.ok) throw new Error(`upload failed (HTTP ${res.status}: ${(await res.text()).slice(0, 120)})`);
      imported += 1;
      console.log(`  added ${p.filename}  [${p.project}]`);
    } catch (err) {
      failed.push(`${p.filename}: ${err.message}`);
      console.log(`  FAILED ${p.filename}: ${err.message}`);
    }
  }

  console.log(`\nDone. ${imported} imported, ${already} already in the library, ${failed.length} failed.`);
  if (failed.length) process.exitCode = 1;
}

main().catch((err) => {
  console.error(`Import stopped: ${err.message}`);
  process.exit(1);
});
