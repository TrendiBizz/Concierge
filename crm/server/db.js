// SQLite storage for Concierge CRM (built-in node:sqlite, no dependencies).
// Multi-tenant: every contact, stage and opportunity belongs to a tenant_id.

import { DatabaseSync } from 'node:sqlite';

const SCHEMA = `
  PRAGMA journal_mode = WAL;

  CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    passcode   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS contacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    email      TEXT NOT NULL DEFAULT '',
    phone      TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    tags       TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS contacts_tenant_idx ON contacts (tenant_id);

  -- One ordered list of stage names per tenant. position is the display
  -- order; an opportunity's stage column stores the stage NAME, not
  -- this id, so renaming a stage does not strand existing opportunities.
  CREATE TABLE IF NOT EXISTS stages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    name      TEXT NOT NULL,
    position  INTEGER NOT NULL
  );

  CREATE INDEX IF NOT EXISTS stages_tenant_idx ON stages (tenant_id);

  CREATE TABLE IF NOT EXISTS opportunities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL,
    contact_id INTEGER NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    value      REAL NOT NULL DEFAULT 0,
    stage      TEXT NOT NULL DEFAULT '',
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS opportunities_tenant_idx ON opportunities (tenant_id);
  CREATE INDEX IF NOT EXISTS opportunities_stage_idx ON opportunities (tenant_id, stage);

  CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
  );
`;

const DEFAULT_STAGES = ['New', 'Contacted', 'Qualified', 'Won', 'Lost'];

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

function contactFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    name: row.name,
    email: row.email,
    phone: row.phone,
    notes: row.notes,
    tags: parseJson(row.tags, []),
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function opportunityFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    contact_id: Number(row.contact_id),
    title: row.title,
    value: Number(row.value),
    stage: row.stage,
    notes: row.notes,
    created_at: row.created_at,
    updated_at: row.updated_at,
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

    listContacts: db.prepare('SELECT * FROM contacts WHERE tenant_id = ? ORDER BY name'),
    getContact: db.prepare('SELECT * FROM contacts WHERE tenant_id = ? AND id = ?'),
    insertContact: db.prepare(
      `INSERT INTO contacts (tenant_id, name, email, phone, notes, tags, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ),
    updateContact: db.prepare(
      `UPDATE contacts SET name = ?, email = ?, phone = ?, notes = ?, tags = ?, updated_at = ?
       WHERE tenant_id = ? AND id = ?`,
    ),
    deleteContact: db.prepare('DELETE FROM contacts WHERE tenant_id = ? AND id = ?'),

    listStages: db.prepare('SELECT * FROM stages WHERE tenant_id = ? ORDER BY position'),
    insertStage: db.prepare('INSERT INTO stages (tenant_id, name, position) VALUES (?, ?, ?)'),
    deleteStages: db.prepare('DELETE FROM stages WHERE tenant_id = ?'),

    listOpportunities: db.prepare('SELECT * FROM opportunities WHERE tenant_id = ? ORDER BY updated_at DESC'),
    getOpportunity: db.prepare('SELECT * FROM opportunities WHERE tenant_id = ? AND id = ?'),
    insertOpportunity: db.prepare(
      `INSERT INTO opportunities (tenant_id, contact_id, title, value, stage, notes, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ),
    updateOpportunity: db.prepare(
      `UPDATE opportunities SET contact_id = ?, title = ?, value = ?, stage = ?, notes = ?, updated_at = ?
       WHERE tenant_id = ? AND id = ?`,
    ),
    deleteOpportunity: db.prepare('DELETE FROM opportunities WHERE tenant_id = ? AND id = ?'),

    getMeta: db.prepare('SELECT value FROM meta WHERE key = ?'),
    setMeta: db.prepare('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)'),
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

    // Runs `seed` once ever per key (used to give each new tenant its
    // default pipeline stages exactly once).
    seedOnce(key, seed) {
      if (stmt.getMeta.get(key)) return false;
      seed();
      stmt.setMeta.run(key, now());
      return true;
    },

    seedDefaultStages(tenantId) {
      this.seedOnce(`stages_${tenantId}_v1`, () => {
        DEFAULT_STAGES.forEach((name, i) => stmt.insertStage.run(tenantId, name, i));
      });
    },

    listStages(tenantId) {
      return stmt.listStages.all(tenantId).map((r) => ({ id: Number(r.id), name: r.name, position: r.position }));
    },

    // Replaces the whole ordered stage list for a tenant. Opportunities
    // keep whatever stage *name* they already had, even if it is no longer
    // in the list -- renaming/removing a stage never silently reassigns
    // existing opportunities.
    saveStages(tenantId, names) {
      stmt.deleteStages.run(tenantId);
      names.forEach((name, i) => stmt.insertStage.run(tenantId, name, i));
      return this.listStages(tenantId);
    },

    listContacts(tenantId) {
      return stmt.listContacts.all(tenantId).map(contactFromRow);
    },

    getContact(tenantId, id) {
      return contactFromRow(stmt.getContact.get(tenantId, id));
    },

    insertContact(tenantId, contact) {
      const stamp = now();
      const result = stmt.insertContact.run(
        tenantId,
        contact.name ?? '',
        contact.email ?? '',
        contact.phone ?? '',
        contact.notes ?? '',
        JSON.stringify(contact.tags ?? []),
        stamp,
        stamp,
      );
      return this.getContact(tenantId, Number(result.lastInsertRowid));
    },

    saveContact(tenantId, contact) {
      stmt.updateContact.run(
        contact.name,
        contact.email,
        contact.phone,
        contact.notes,
        JSON.stringify(contact.tags),
        now(),
        tenantId,
        contact.id,
      );
      return this.getContact(tenantId, contact.id);
    },

    deleteContact(tenantId, id) {
      return stmt.deleteContact.run(tenantId, id).changes > 0;
    },

    listOpportunities(tenantId) {
      return stmt.listOpportunities.all(tenantId).map(opportunityFromRow);
    },

    getOpportunity(tenantId, id) {
      return opportunityFromRow(stmt.getOpportunity.get(tenantId, id));
    },

    insertOpportunity(tenantId, opp) {
      const stamp = now();
      const result = stmt.insertOpportunity.run(
        tenantId,
        opp.contact_id,
        opp.title ?? '',
        opp.value ?? 0,
        opp.stage ?? '',
        opp.notes ?? '',
        stamp,
        stamp,
      );
      return this.getOpportunity(tenantId, Number(result.lastInsertRowid));
    },

    saveOpportunity(tenantId, opp) {
      stmt.updateOpportunity.run(opp.contact_id, opp.title, opp.value, opp.stage, opp.notes, now(), tenantId, opp.id);
      return this.getOpportunity(tenantId, opp.id);
    },

    deleteOpportunity(tenantId, id) {
      return stmt.deleteOpportunity.run(tenantId, id).changes > 0;
    },
  };
}
