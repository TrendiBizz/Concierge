// End-to-end tests: starts the real server on a random port with a temp data folder.
// Run with: npm test   (from the server folder)

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, describe, it } from 'node:test';
import { fileURLToPath } from 'node:url';

const serverFile = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'server.js');
const PORT = 41000 + Math.floor(Math.random() * 2000);
const BASE = `http://127.0.0.1:${PORT}`;
const PASSCODE = 'TESTPASS';
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64',
);

let child;
let dataDir;
let token = '';

async function api(method, route, body, { raw, headers = {}, auth = true } = {}) {
  const init = { method, headers: { ...headers } };
  if (auth && token) init.headers.Authorization = `Bearer ${token}`;
  if (raw !== undefined) {
    init.body = raw;
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE}${route}`, init);
  const type = res.headers.get('content-type') || '';
  const data = type.includes('json') ? await res.json() : await res.arrayBuffer();
  return { status: res.status, data, res };
}

function future(hours = 24) {
  return new Date(Date.now() + hours * 3600_000).toISOString();
}

before(async () => {
  dataDir = mkdtempSync(path.join(tmpdir(), 'socialsync-test-'));
  child = spawn(process.execPath, [serverFile], {
    env: { ...process.env, PORT: String(PORT), DATA_DIR: dataDir, SOCIALSYNC_PASSCODE: PASSCODE },
    stdio: 'ignore',
  });
  for (let i = 0; i < 50; i += 1) {
    try {
      const res = await fetch(`${BASE}/api/health`);
      if (res.ok) return;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('Server did not start');
});

after(() => {
  if (child) child.kill();
  if (dataDir) rmSync(dataDir, { recursive: true, force: true });
});

describe('auth', () => {
  it('health is public, everything else needs a token', async () => {
    assert.equal((await api('GET', '/api/health', undefined, { auth: false })).status, 200);
    assert.equal((await api('GET', '/api/posts', undefined, { auth: false })).status, 401);
    assert.equal((await api('GET', '/media/1', undefined, { auth: false })).status, 401);
  });

  it('rejects a wrong passcode and accepts the right one (case-insensitive)', async () => {
    const bad = await api('POST', '/api/login', { passcode: 'nope' }, { auth: false });
    assert.equal(bad.status, 401);
    const good = await api('POST', '/api/login', { passcode: PASSCODE.toLowerCase() }, { auth: false });
    assert.equal(good.status, 200);
    assert.ok(good.data.token);
    assert.match(good.res.headers.get('set-cookie') || '', /ss_token=/);
    token = good.data.token;
  });
});

describe('guardrails', () => {
  it('blocks a years-in-business claim that contradicts the owner', async () => {
    const { data } = await api('POST', '/api/check', {
      content: 'We have 25 years of experience in recladding.',
      platforms: ['facebook'],
    });
    assert.equal(data.check.ok, false);
    assert.ok(data.check.errors.some((e) => e.code === 'unverified_claim'));
  });

  it('accepts the verified claim "more than 10 years"', async () => {
    const { data } = await api('POST', '/api/check', {
      content: 'Auckland recladding specialists with more than 10 years on the tools.',
      platforms: ['facebook'],
    });
    assert.equal(data.check.ok, true);
  });

  it('blocks forbidden phrases', async () => {
    const { data } = await api('POST', '/api/check', {
      content: "We're Auckland's best recladding team.",
      platforms: ['facebook'],
    });
    assert.ok(data.check.errors.some((e) => e.code === 'forbidden_phrase'));
  });

  it('warns (but does not block) on unverified claims and phone calls', async () => {
    const { data } = await api('POST', '/api/check', {
      content: 'Preferred Nu-Wall installer with a 25 year warranty. Call us today!',
      platforms: ['linkedin'],
    });
    const codes = data.check.warnings.map((w) => w.code);
    assert.ok(codes.includes('nuwall_status'));
    assert.ok(codes.includes('warranty'));
    assert.ok(codes.includes('phone_cta'));
    assert.equal(data.check.ok, true);
  });

  it('requires media for Instagram and counts an X link as 23 characters', async () => {
    const ig = await api('POST', '/api/check', { content: 'Hello', platforms: ['instagram'] });
    assert.ok(ig.data.check.errors.some((e) => e.code === 'media_required'));

    const link = 'https://pukekoconstruction.co.nz/some/very/long/path/that/is/much/longer/than/twenty-three';
    const content = 'x'.repeat(250);
    const x = await api('POST', '/api/check', { content, link, platforms: ['twitter'] });
    assert.equal(x.data.check.platforms.twitter.length, 250 + 1 + 23);
    assert.equal(x.data.check.platforms.twitter.over, false);

    const tooLong = await api('POST', '/api/check', { content: 'x'.repeat(260), link, platforms: ['twitter'] });
    assert.ok(tooLong.data.check.errors.some((e) => e.code === 'over_limit'));
  });
});

describe('social pages', () => {
  let linkedinId;

  it('starts with the pages found on the Pukeko website', async () => {
    const { data } = await api('GET', '/api/channels');
    const platforms = data.channels.map((c) => c.platform);
    assert.ok(platforms.includes('facebook'));
    assert.ok(platforms.includes('instagram'));
    assert.ok(data.platforms.includes('linkedin'));
    assert.ok(data.channels.find((c) => c.platform === 'facebook').url.startsWith('https://www.facebook.com/'));
  });

  it('adds a LinkedIn page and edits it', async () => {
    const created = await api('POST', '/api/channels', {
      platform: 'linkedin',
      name: 'Pukeko Construction',
      url: 'https://www.linkedin.com/company/pukeko-construction',
    });
    assert.equal(created.status, 201);
    linkedinId = created.data.channel.id;

    const edited = await api('PUT', `/api/channels/${linkedinId}`, { notes: 'Company page' });
    assert.equal(edited.status, 200);
    assert.equal(edited.data.channel.notes, 'Company page');
    assert.equal(edited.data.channel.platform, 'linkedin');
  });

  it('rejects bad links and unknown platforms', async () => {
    const noScheme = await api('POST', '/api/channels', { platform: 'linkedin', name: 'x', url: 'linkedin.com/x' });
    assert.equal(noScheme.status, 400);
    const script = await api('POST', '/api/channels', { platform: 'linkedin', name: 'x', url: 'javascript:alert(1)' });
    assert.equal(script.status, 400);
    const unknown = await api('POST', '/api/channels', { platform: 'myspace', name: 'x', url: 'https://example.com' });
    assert.equal(unknown.status, 400);
  });

  it('deletes a page, and deleted defaults do not come back', async () => {
    assert.equal((await api('DELETE', `/api/channels/${linkedinId}`)).status, 200);
    assert.equal((await api('DELETE', `/api/channels/${linkedinId}`)).status, 404);
    const { data } = await api('GET', '/api/channels');
    const website = data.channels.find((c) => c.platform === 'website');
    assert.equal((await api('DELETE', `/api/channels/${website.id}`)).status, 200);
    const again = await api('GET', '/api/channels');
    assert.ok(!again.data.channels.some((c) => c.platform === 'website'));
  });
});

describe('posts and scheduling', () => {
  let postId;
  let mediaId;

  it('saves a draft even when it has problems', async () => {
    const { status, data } = await api('POST', '/api/posts', {
      content: 'Draft about recladding',
      platforms: ['instagram'],
    });
    assert.equal(status, 201);
    assert.equal(data.post.status, 'draft');
    assert.equal(data.check.ok, false);
    postId = data.post.id;
  });

  it('refuses to schedule while there are errors, and rejects past times', async () => {
    const blocked = await api('POST', `/api/posts/${postId}/schedule`, { scheduled_at: future() });
    assert.equal(blocked.status, 422);
    assert.ok(blocked.data.problems.some((p) => /photo or video/.test(p)));

    const past = await api('POST', `/api/posts/${postId}/schedule`, {
      scheduled_at: new Date(Date.now() - 3600_000).toISOString(),
    });
    assert.equal(past.status, 400);
  });

  it('uploads a photo, lists it and serves it with a query token and range support', async () => {
    const up = await api(
      'POST',
      '/api/media?filename=before.png&caption=Before&project=Ponsonby',
      undefined,
      { raw: PNG, headers: { 'Content-Type': 'image/png' } },
    );
    assert.equal(up.status, 201);
    mediaId = up.data.media.id;
    assert.equal(up.data.media.project, 'Ponsonby');
    assert.equal(up.data.media.path, undefined, 'disk path must not leak');

    const list = await api('GET', '/api/media');
    assert.equal(list.data.media.length, 1);

    const full = await fetch(`${BASE}/media/${mediaId}?token=${token}`);
    assert.equal(full.status, 200);
    assert.equal(Buffer.from(await full.arrayBuffer()).length, PNG.length);

    const part = await fetch(`${BASE}/media/${mediaId}?token=${token}`, { headers: { Range: 'bytes=0-7' } });
    assert.equal(part.status, 206);
    assert.equal(Buffer.from(await part.arrayBuffer()).length, 8);
  });

  it('rejects unsupported uploads', async () => {
    const bad = await api('POST', '/api/media', undefined, {
      raw: Buffer.from('<svg/>'),
      headers: { 'Content-Type': 'image/svg+xml' },
    });
    assert.equal(bad.status, 415);
  });

  it('schedules once fixed, then lists and edits it', async () => {
    const fixed = await api('PUT', `/api/posts/${postId}`, {
      content: 'Before and after: a full recladding in Ponsonby.',
      media_ids: [mediaId],
    });
    assert.equal(fixed.status, 200);
    assert.equal(fixed.data.check.ok, true);

    const when = future(48);
    const scheduled = await api('POST', `/api/posts/${postId}/schedule`, { scheduled_at: when });
    assert.equal(scheduled.status, 200);
    assert.equal(scheduled.data.post.status, 'scheduled');
    assert.equal(scheduled.data.post.scheduled_at, when);

    const onlyScheduled = await api('GET', '/api/posts?status=scheduled');
    assert.equal(onlyScheduled.data.posts.length, 1);

    const breaks = await api('PUT', `/api/posts/${postId}`, { platforms: [] });
    assert.equal(breaks.status, 422, 'a scheduled post must stay valid');
  });

  it('will not delete a photo that an unposted post still uses', async () => {
    const res = await api('DELETE', `/api/media/${mediaId}`);
    assert.equal(res.status, 409);
  });

  it('marks posted, locks editing, duplicates and cleans up', async () => {
    const posted = await api('POST', `/api/posts/${postId}/mark-posted`);
    assert.equal(posted.data.post.status, 'posted');
    assert.ok(posted.data.post.posted_at);

    assert.equal((await api('PUT', `/api/posts/${postId}`, { content: 'changed' })).status, 409);
    assert.equal((await api('POST', `/api/posts/${postId}/unschedule`)).status, 409);

    const dup = await api('POST', `/api/posts/${postId}/duplicate`);
    assert.equal(dup.status, 201);
    assert.equal(dup.data.post.status, 'draft');
    assert.deepEqual(dup.data.post.media_ids, [mediaId]);

    // The duplicate (a draft) still uses the photo, so it stays protected.
    assert.equal((await api('DELETE', `/api/media/${mediaId}`)).status, 409);
    assert.equal((await api('DELETE', `/api/posts/${dup.data.post.id}`)).status, 200);
    assert.equal((await api('DELETE', `/api/media/${mediaId}`)).status, 200);
    assert.equal((await api('GET', `/media/${mediaId}`)).status, 404);
  });

  it('serves the web dashboard and blocks path traversal', async () => {
    const home = await fetch(`${BASE}/`);
    assert.ok([200, 404].includes(home.status));
    const evil = await fetch(`${BASE}/..%2Fserver%2Fserver.js`);
    assert.equal(evil.status, 404);
  });
});
