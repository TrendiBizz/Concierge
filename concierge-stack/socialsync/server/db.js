// SQLite storage for SocialSync (built-in node:sqlite, no dependencies).
// Multi-tenant: every post, media item and channel belongs to a tenant_id
// (one tenant per Concierge customer; Pukeko Construction is tenant 'pukeko').

import { DatabaseSync } from 'node:sqlite';

// Table creation only. Indexes that touch tenant_id are created separately,
// after the column-upgrade step below, because an older database file may
// already have these tables without that column -- CREATE TABLE IF NOT
// EXISTS is then a no-op and an index on a not-yet-existing column fails.
const SCHEMA = `
  PRAGMA journal_mode = WAL;

  CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    passcode   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS tenant_rules (
    tenant_id        TEXT PRIMARY KEY,
    facts            TEXT NOT NULL DEFAULT '[]',
    forbidden_phrases TEXT NOT NULL DEFAULT '[]',
    warnings         TEXT NOT NULL DEFAULT '[]',
    updated_at       TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    TEXT NOT NULL DEFAULT 'pukeko',
    content      TEXT NOT NULL DEFAULT '',
    link         TEXT NOT NULL DEFAULT '',
    hashtags     TEXT NOT NULL DEFAULT '',
    platforms    TEXT NOT NULL DEFAULT '[]',
    media_ids    TEXT NOT NULL DEFAULT '[]',
    status       TEXT NOT NULL DEFAULT 'draft',
    scheduled_at TEXT,
    posted_at    TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS posts_status_idx ON posts (status);
  CREATE INDEX IF NOT EXISTS posts_scheduled_idx ON posts (scheduled_at);

  CREATE TABLE IF NOT EXISTS media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL DEFAULT 'pukeko',
    filename   TEXT NOT NULL,
    mime       TEXT NOT NULL,
    size       INTEGER NOT NULL,
    caption    TEXT NOT NULL DEFAULT '',
    project    TEXT NOT NULL DEFAULT '',
    path       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS channels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL DEFAULT 'pukeko',
    platform   TEXT NOT NULL,
    name       TEXT NOT NULL,
    url        TEXT NOT NULL,
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
`;

const TENANT_INDEXES = `
  CREATE INDEX IF NOT EXISTS posts_tenant_idx ON posts (tenant_id);
  CREATE INDEX IF NOT EXISTS media_tenant_idx ON media (tenant_id);
  CREATE INDEX IF NOT EXISTS channels_tenant_idx ON channels (tenant_id);
`;

// Adds a column to an existing table when an older database file predates it.
// SQLite's CREATE TABLE IF NOT EXISTS never adds columns to a table that
// already exists, so a one-time ALTER TABLE is needed for upgrades in place.
function ensureColumn(db, table, column, ddl) {
  const cols = db.prepare(`PRAGMA table_info(${table})`).all();
  if (!cols.some((c) => c.name === column)) {
    db.exec(`ALTER TABLE ${table} ADD COLUMN ${ddl}`);
  }
}

function parseJson(text, fallback) {
  try {
    const value = JSON.parse(text);
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function postFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    content: row.content,
    link: row.link,
    hashtags: row.hashtags,
    platforms: parseJson(row.platforms, []),
    media_ids: parseJson(row.media_ids, []),
    status: row.status,
    scheduled_at: row.scheduled_at,
    posted_at: row.posted_at,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function mediaFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    filename: row.filename,
    mime: row.mime,
    size: Number(row.size),
    caption: row.caption,
    project: row.project,
    created_at: row.created_at,
    url: `/media/${Number(row.id)}`,
  };
}

function tenantFromRow(row) {
  return row ? { id: row.id, name: row.name, passcode: row.passcode, created_at: row.created_at } : null;
}

function tenantRulesFromRow(row) {
  if (!row) return null;
  return {
    tenant_id: row.tenant_id,
    facts: parseJson(row.facts, []),
    forbidden_phrases: parseJson(row.forbidden_phrases, []),
    warnings: parseJson(row.warnings, []),
  };
}

export function openDb(file) {
  const db = new DatabaseSync(file);
  db.exec(SCHEMA);
  // Upgrade path for a database created before multi-tenancy existed.
  ensureColumn(db, 'posts', 'tenant_id', "tenant_id TEXT NOT NULL DEFAULT 'pukeko'");
  ensureColumn(db, 'media', 'tenant_id', "tenant_id TEXT NOT NULL DEFAULT 'pukeko'");
  ensureColumn(db, 'channels', 'tenant_id', "tenant_id TEXT NOT NULL DEFAULT 'pukeko'");
  ensureColumn(db, 'tenants', 'passcode', "passcode TEXT NOT NULL DEFAULT ''");
  db.exec(TENANT_INDEXES);
  return db;
}

export function makeStore(db) {
  const stmt = {
    listPosts: db.prepare(
      'SELECT * FROM posts WHERE tenant_id = ? ORDER BY COALESCE(scheduled_at, created_at) DESC, id DESC',
    ),
    getPost: db.prepare('SELECT * FROM posts WHERE tenant_id = ? AND id = ?'),
    insertPost: db.prepare(
      `INSERT INTO posts (tenant_id, content, link, hashtags, platforms, media_ids, status, scheduled_at, posted_at, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ),
    updatePost: db.prepare(
      `UPDATE posts SET content = ?, link = ?, hashtags = ?, platforms = ?, media_ids = ?,
         status = ?, scheduled_at = ?, posted_at = ?, updated_at = ?
       WHERE tenant_id = ? AND id = ?`,
    ),
    deletePost: db.prepare('DELETE FROM posts WHERE tenant_id = ? AND id = ?'),
    duePostsAcrossTenants: db.prepare(
      "SELECT * FROM posts WHERE status = 'scheduled' AND scheduled_at <= ? ORDER BY scheduled_at",
    ),
    listMedia: db.prepare('SELECT * FROM media WHERE tenant_id = ? ORDER BY id DESC'),
    getMedia: db.prepare('SELECT * FROM media WHERE tenant_id = ? AND id = ?'),
    insertMedia: db.prepare(
      `INSERT INTO media (tenant_id, filename, mime, size, caption, project, path, created_at)
       VALUES (?, ?, ?, ?, ?, ?, '', ?)`,
    ),
    setMediaPath: db.prepare('UPDATE media SET path = ? WHERE tenant_id = ? AND id = ?'),
    updateMedia: db.prepare('UPDATE media SET caption = ?, project = ? WHERE tenant_id = ? AND id = ?'),
    deleteMedia: db.prepare('DELETE FROM media WHERE tenant_id = ? AND id = ?'),
    listChannels: db.prepare('SELECT * FROM channels WHERE tenant_id = ? ORDER BY id'),
    getChannel: db.prepare('SELECT * FROM channels WHERE tenant_id = ? AND id = ?'),
    insertChannel: db.prepare(
      `INSERT INTO channels (tenant_id, platform, name, url, notes, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ),
    updateChannel: db.prepare(
      'UPDATE channels SET platform = ?, name = ?, url = ?, notes = ?, updated_at = ? WHERE tenant_id = ? AND id = ?',
    ),
    deleteChannel: db.prepare('DELETE FROM channels WHERE tenant_id = ? AND id = ?'),
    getMeta: db.prepare('SELECT value FROM meta WHERE key = ?'),
    setMeta: db.prepare('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)'),
    getTenant: db.prepare('SELECT * FROM tenants WHERE id = ?'),
    getTenantByPasscode: db.prepare('SELECT * FROM tenants WHERE UPPER(passcode) = UPPER(?)'),
    insertTenant: db.prepare('INSERT INTO tenants (id, name, passcode, created_at) VALUES (?, ?, ?, ?)'),
    setTenantPasscode: db.prepare('UPDATE tenants SET passcode = ? WHERE id = ?'),
    listTenants: db.prepare('SELECT * FROM tenants ORDER BY created_at'),
    getTenantRules: db.prepare('SELECT * FROM tenant_rules WHERE tenant_id = ?'),
    upsertTenantRules: db.prepare(
      `INSERT INTO tenant_rules (tenant_id, facts, forbidden_phrases, warnings, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(tenant_id) DO UPDATE SET facts = excluded.facts,
         forbidden_phrases = excluded.forbidden_phrases, warnings = excluded.warnings, updated_at = excluded.updated_at`,
    ),
  };

  const channelFromRow = (row) =>
    row
      ? {
          id: Number(row.id),
          tenant_id: row.tenant_id,
          platform: row.platform,
          name: row.name,
          url: row.url,
          notes: row.notes,
          created_at: row.created_at,
          updated_at: row.updated_at,
        }
      : null;

  const now = () => new Date().toISOString();

  return {
    // ---------------------------------------------------------- tenants

    getTenant(id) {
      return tenantFromRow(stmt.getTenant.get(id));
    },

    getTenantByPasscode(passcode) {
      return tenantFromRow(stmt.getTenantByPasscode.get(passcode));
    },

    listTenants() {
      return stmt.listTenants.all().map(tenantFromRow);
    },

    // Creates a new customer with this id and passcode (both already chosen
    // by the caller -- server.js picks a free slug and a random passcode).
    insertTenant(id, name, passcode) {
      stmt.insertTenant.run(id, name || id, passcode, now());
      return this.getTenant(id);
    },

    // Used once, at startup, to move Pukeko's existing single shared
    // passcode into the tenants table so every tenant uses the same login.
    setTenantPasscode(id, passcode) {
      stmt.setTenantPasscode.run(passcode, id);
      return this.getTenant(id);
    },

    getTenantRules(tenantId) {
      return tenantRulesFromRow(stmt.getTenantRules.get(tenantId)) ?? {
        tenant_id: tenantId,
        facts: [],
        forbidden_phrases: [],
        warnings: [],
      };
    },

    saveTenantRules(tenantId, { facts, forbidden_phrases, warnings }) {
      stmt.upsertTenantRules.run(
        tenantId,
        JSON.stringify(facts ?? []),
        JSON.stringify(forbidden_phrases ?? []),
        JSON.stringify(warnings ?? []),
        now(),
      );
      return this.getTenantRules(tenantId);
    },

    // ---------------------------------------------------------- posts

    listPosts(tenantId) {
      return stmt.listPosts.all(tenantId).map(postFromRow);
    },

    getPost(tenantId, id) {
      return postFromRow(stmt.getPost.get(tenantId, id));
    },

    insertPost(tenantId, post) {
      const stamp = now();
      const result = stmt.insertPost.run(
        tenantId,
        post.content ?? '',
        post.link ?? '',
        post.hashtags ?? '',
        JSON.stringify(post.platforms ?? []),
        JSON.stringify(post.media_ids ?? []),
        post.status ?? 'draft',
        post.scheduled_at ?? null,
        post.posted_at ?? null,
        stamp,
        stamp,
      );
      return this.getPost(tenantId, Number(result.lastInsertRowid));
    },

    savePost(tenantId, post) {
      stmt.updatePost.run(
        post.content,
        post.link,
        post.hashtags,
        JSON.stringify(post.platforms),
        JSON.stringify(post.media_ids),
        post.status,
        post.scheduled_at ?? null,
        post.posted_at ?? null,
        now(),
        tenantId,
        post.id,
      );
      return this.getPost(tenantId, post.id);
    },

    deletePost(tenantId, id) {
      return stmt.deletePost.run(tenantId, id).changes > 0;
    },

    // Every tenant's posts that are scheduled and due now or in the past.
    // Used by the reminder scheduler, which has no single tenant of its own.
    duePostsAcrossTenants() {
      return stmt.duePostsAcrossTenants.all(now()).map(postFromRow);
    },

    // ---------------------------------------------------------- media

    listMedia(tenantId) {
      return stmt.listMedia.all(tenantId).map(mediaFromRow);
    },

    getMedia(tenantId, id) {
      return mediaFromRow(stmt.getMedia.get(tenantId, id));
    },

    // Internal: the on-disk path is never exposed through the API.
    getMediaPath(tenantId, id) {
      const row = stmt.getMedia.get(tenantId, id);
      return row ? row.path : null;
    },

    insertMedia(tenantId, media) {
      const result = stmt.insertMedia.run(
        tenantId,
        media.filename,
        media.mime,
        media.size,
        media.caption ?? '',
        media.project ?? '',
        now(),
      );
      return Number(result.lastInsertRowid);
    },

    setMediaPath(tenantId, id, filePath) {
      stmt.setMediaPath.run(filePath, tenantId, id);
    },

    saveMedia(tenantId, id, { caption, project }) {
      stmt.updateMedia.run(caption, project, tenantId, id);
      return this.getMedia(tenantId, id);
    },

    deleteMedia(tenantId, id) {
      return stmt.deleteMedia.run(tenantId, id).changes > 0;
    },

    // ---------------------------------------------------------- channels

    listChannels(tenantId) {
      return stmt.listChannels.all(tenantId).map(channelFromRow);
    },

    getChannel(tenantId, id) {
      return channelFromRow(stmt.getChannel.get(tenantId, id));
    },

    insertChannel(tenantId, channel) {
      const stamp = now();
      const result = stmt.insertChannel.run(
        tenantId,
        channel.platform,
        channel.name,
        channel.url,
        channel.notes ?? '',
        stamp,
        stamp,
      );
      return this.getChannel(tenantId, Number(result.lastInsertRowid));
    },

    saveChannel(tenantId, channel) {
      stmt.updateChannel.run(channel.platform, channel.name, channel.url, channel.notes, now(), tenantId, channel.id);
      return this.getChannel(tenantId, channel.id);
    },

    deleteChannel(tenantId, id) {
      return stmt.deleteChannel.run(tenantId, id).changes > 0;
    },

    // Runs `seed` once ever per key (a deleted default page never comes back).
    seedOnce(key, seed) {
      if (stmt.getMeta.get(key)) return false;
      seed();
      stmt.setMeta.run(key, now());
      return true;
    },

    // Posts that still need this media (anything not yet marked as posted).
    postsUsingMedia(tenantId, id) {
      return this.listPosts(tenantId).filter(
        (post) => post.status !== 'posted' && post.media_ids.includes(id),
      );
    },
  };
}
