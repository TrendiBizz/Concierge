// SQLite storage for Concierge Workflows (built-in node:sqlite, no deps).
// Multi-tenant: every workflow and run belongs to a tenant_id.

import { DatabaseSync } from 'node:sqlite';

const SCHEMA = `
  PRAGMA journal_mode = WAL;

  CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    passcode   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  -- actions: JSON array of {type: "log"|"webhook", ...type-specific fields}.
  CREATE TABLE IF NOT EXISTS workflows (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1,
    actions    TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS workflows_tenant_idx ON workflows (tenant_id);
  CREATE INDEX IF NOT EXISTS workflows_event_idx ON workflows (tenant_id, event_type);

  -- One row per workflow firing for one event. results: JSON array of
  -- {type, ok, detail} in action order.
  CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT NOT NULL,
    workflow_id INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    event_data  TEXT NOT NULL DEFAULT '{}',
    results     TEXT NOT NULL DEFAULT '[]',
    ok          INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS runs_tenant_idx ON runs (tenant_id);
  CREATE INDEX IF NOT EXISTS runs_workflow_idx ON runs (tenant_id, workflow_id);
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

function workflowFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    name: row.name,
    event_type: row.event_type,
    enabled: Boolean(row.enabled),
    actions: parseJson(row.actions, []),
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

function runFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    workflow_id: Number(row.workflow_id),
    event_type: row.event_type,
    event_data: parseJson(row.event_data, {}),
    results: parseJson(row.results, []),
    ok: Boolean(row.ok),
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

    listWorkflows: db.prepare('SELECT * FROM workflows WHERE tenant_id = ? ORDER BY created_at DESC'),
    listWorkflowsForEvent: db.prepare(
      'SELECT * FROM workflows WHERE tenant_id = ? AND event_type = ? AND enabled = 1',
    ),
    getWorkflow: db.prepare('SELECT * FROM workflows WHERE tenant_id = ? AND id = ?'),
    insertWorkflow: db.prepare(
      `INSERT INTO workflows (tenant_id, name, event_type, enabled, actions, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ),
    updateWorkflow: db.prepare(
      `UPDATE workflows SET name = ?, event_type = ?, enabled = ?, actions = ?, updated_at = ?
       WHERE tenant_id = ? AND id = ?`,
    ),
    deleteWorkflow: db.prepare('DELETE FROM workflows WHERE tenant_id = ? AND id = ?'),

    insertRun: db.prepare(
      `INSERT INTO runs (tenant_id, workflow_id, event_type, event_data, results, ok, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ),
    listRuns: db.prepare('SELECT * FROM runs WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 200'),
    listRunsForWorkflow: db.prepare(
      'SELECT * FROM runs WHERE tenant_id = ? AND workflow_id = ? ORDER BY created_at DESC LIMIT 200',
    ),
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

    listWorkflows(tenantId) {
      return stmt.listWorkflows.all(tenantId).map(workflowFromRow);
    },

    listWorkflowsForEvent(tenantId, eventType) {
      return stmt.listWorkflowsForEvent.all(tenantId, eventType).map(workflowFromRow);
    },

    getWorkflow(tenantId, id) {
      return workflowFromRow(stmt.getWorkflow.get(tenantId, id));
    },

    insertWorkflow(tenantId, wf) {
      const stamp = now();
      const result = stmt.insertWorkflow.run(
        tenantId,
        wf.name ?? '',
        wf.event_type,
        wf.enabled ? 1 : 0,
        JSON.stringify(wf.actions ?? []),
        stamp,
        stamp,
      );
      return this.getWorkflow(tenantId, Number(result.lastInsertRowid));
    },

    saveWorkflow(tenantId, id, wf) {
      stmt.updateWorkflow.run(wf.name, wf.event_type, wf.enabled ? 1 : 0, JSON.stringify(wf.actions), now(), tenantId, id);
      return this.getWorkflow(tenantId, id);
    },

    deleteWorkflow(tenantId, id) {
      return stmt.deleteWorkflow.run(tenantId, id).changes > 0;
    },

    recordRun(tenantId, workflowId, eventType, eventData, results, ok) {
      stmt.insertRun.run(tenantId, workflowId, eventType, JSON.stringify(eventData ?? {}), JSON.stringify(results ?? []), ok ? 1 : 0, now());
    },

    listRuns(tenantId) {
      return stmt.listRuns.all(tenantId).map(runFromRow);
    },

    listRunsForWorkflow(tenantId, workflowId) {
      return stmt.listRunsForWorkflow.all(tenantId, workflowId).map(runFromRow);
    },
  };
}
