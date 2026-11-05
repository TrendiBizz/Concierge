// SQLite storage for Concierge Sites (built-in node:sqlite, no deps).
// Multi-tenant: every page, block and lead belongs to a tenant_id.

import { DatabaseSync } from 'node:sqlite';

const SCHEMA = `
  PRAGMA journal_mode = WAL;

  CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    passcode   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS pages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL,
    slug       TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS pages_tenant_idx ON pages (tenant_id);
  CREATE UNIQUE INDEX IF NOT EXISTS pages_tenant_slug_idx ON pages (tenant_id, slug);

  -- type: heading | paragraph | image | button | form
  -- content: JSON, shape depends on type (see server.js BLOCK_SCHEMAS).
  CREATE TABLE IF NOT EXISTS blocks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    page_id   INTEGER NOT NULL,
    type      TEXT NOT NULL,
    content   TEXT NOT NULL DEFAULT '{}',
    position  INTEGER NOT NULL DEFAULT 0
  );

  CREATE INDEX IF NOT EXISTS blocks_page_idx ON blocks (tenant_id, page_id);

  -- A submission of a page's lead-capture form.
  CREATE TABLE IF NOT EXISTS leads (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL,
    page_id    INTEGER NOT NULL,
    data       TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS leads_tenant_idx ON leads (tenant_id);
  CREATE INDEX IF NOT EXISTS leads_page_idx ON leads (tenant_id, page_id);
`;

function parseJson(text, fallback) {
  try {
    const value = JSON.parse(text);
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function tenantFromRow(row) {
  return row ? { id: row.id, name: row.name, passcode: row.passcode, created_at: row.created_at } : null;
}

function pageFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    slug: row.slug,
    title: row.title,
    status: row.status,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function blockFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    page_id: Number(row.page_id),
    type: row.type,
    content: parseJson(row.content, {}),
    position: Number(row.position),
  };
}

function leadFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    page_id: Number(row.page_id),
    data: parseJson(row.data, {}),
    created_at: row.created_at,
  };
}

export function openDb(file) {
  const db = new DatabaseSync(file);
  db.exec(SCHEMA);
  return db;
}

export function makeStore(db) {
  const stmt = {
    getTenant: db.prepare('SELECT * FROM tenants WHERE id = ?'),
    getTenantByPasscode: db.prepare('SELECT * FROM tenants WHERE UPPER(passcode) = UPPER(?)'),
    insertTenant: db.prepare('INSERT INTO tenants (id, name, passcode, created_at) VALUES (?, ?, ?, ?)'),
    listTenants: db.prepare('SELECT * FROM tenants ORDER BY created_at'),

    listPages: db.prepare('SELECT * FROM pages WHERE tenant_id = ? ORDER BY created_at DESC'),
    getPage: db.prepare('SELECT * FROM pages WHERE tenant_id = ? AND id = ?'),
    getPageBySlug: db.prepare('SELECT * FROM pages WHERE tenant_id = ? AND slug = ?'),
    insertPage: db.prepare(
      "INSERT INTO pages (tenant_id, slug, title, status, created_at, updated_at) VALUES (?, ?, ?, 'draft', ?, ?)",
    ),
    updatePageMeta: db.prepare('UPDATE pages SET title = ?, updated_at = ? WHERE tenant_id = ? AND id = ?'),
    updatePageStatus: db.prepare('UPDATE pages SET status = ?, updated_at = ? WHERE tenant_id = ? AND id = ?'),
    deletePage: db.prepare('DELETE FROM pages WHERE tenant_id = ? AND id = ?'),

    listBlocks: db.prepare('SELECT * FROM blocks WHERE tenant_id = ? AND page_id = ? ORDER BY position'),
    deleteBlocks: db.prepare('DELETE FROM blocks WHERE tenant_id = ? AND page_id = ?'),
    insertBlock: db.prepare('INSERT INTO blocks (tenant_id, page_id, type, content, position) VALUES (?, ?, ?, ?, ?)'),

    insertLead: db.prepare('INSERT INTO leads (tenant_id, page_id, data, created_at) VALUES (?, ?, ?, ?)'),
    listLeads: db.prepare('SELECT * FROM leads WHERE tenant_id = ? ORDER BY created_at DESC'),
    listLeadsForPage: db.prepare('SELECT * FROM leads WHERE tenant_id = ? AND page_id = ? ORDER BY created_at DESC'),
  };

  const now = () => new Date().toISOString();

  return {
    getTenant(id) {
      return tenantFromRow(stmt.getTenant.get(id));
    },

    getTenantByPasscode(passcode) {
      return tenantFromRow(stmt.getTenantByPasscode.get(passcode));
    },

    listTenants() {
      return stmt.listTenants.all().map(tenantFromRow);
    },

    insertTenant(id, name, passcode) {
      stmt.insertTenant.run(id, name || id, passcode, now());
      return this.getTenant(id);
    },

    listPages(tenantId) {
      return stmt.listPages.all(tenantId).map(pageFromRow);
    },

    getPage(tenantId, id) {
      return pageFromRow(stmt.getPage.get(tenantId, id));
    },

    getPageBySlug(tenantId, slug) {
      return pageFromRow(stmt.getPageBySlug.get(tenantId, slug));
    },

    insertPage(tenantId, { slug, title }) {
      const stamp = now();
      const result = stmt.insertPage.run(tenantId, slug, title ?? '', stamp, stamp);
      return this.getPage(tenantId, Number(result.lastInsertRowid));
    },

    savePageMeta(tenantId, id, { title }) {
      stmt.updatePageMeta.run(title, now(), tenantId, id);
      return this.getPage(tenantId, id);
    },

    setPageStatus(tenantId, id, status) {
      stmt.updatePageStatus.run(status, now(), tenantId, id);
      return this.getPage(tenantId, id);
    },

    deletePage(tenantId, id) {
      stmt.deleteBlocks.run(tenantId, id);
      return stmt.deletePage.run(tenantId, id).changes > 0;
    },

    listBlocks(tenantId, pageId) {
      return stmt.listBlocks.all(tenantId, pageId).map(blockFromRow);
    },

    // Replaces every block on a page in one go -- simplest correct model
    // for a block list the dashboard edits as a whole (add/remove/reorder).
    replaceBlocks(tenantId, pageId, blocks) {
      stmt.deleteBlocks.run(tenantId, pageId);
      blocks.forEach((b, i) => stmt.insertBlock.run(tenantId, pageId, b.type, JSON.stringify(b.content ?? {}), i));
      return this.listBlocks(tenantId, pageId);
    },

    insertLead(tenantId, pageId, data) {
      stmt.insertLead.run(tenantId, pageId, JSON.stringify(data ?? {}), now());
    },

    listLeads(tenantId) {
      return stmt.listLeads.all(tenantId).map(leadFromRow);
    },

    listLeadsForPage(tenantId, pageId) {
      return stmt.listLeadsForPage.all(tenantId, pageId).map(leadFromRow);
    },
  };
}
