// SQLite storage for Concierge Calendars (built-in node:sqlite, no deps).
// Multi-tenant: every availability window and appointment belongs to a tenant_id.

import { DatabaseSync } from 'node:sqlite';

const SCHEMA = `
  PRAGMA journal_mode = WAL;

  CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    passcode   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  -- One row per recurring weekly availability window, e.g. Monday 09:00-17:00.
  -- weekday: 0=Sunday .. 6=Saturday (matches JS Date#getDay()).
  -- start_minutes/end_minutes: minutes since local midnight.
  CREATE TABLE IF NOT EXISTS windows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     TEXT NOT NULL,
    weekday       INTEGER NOT NULL,
    start_minutes INTEGER NOT NULL,
    end_minutes   INTEGER NOT NULL,
    slot_minutes  INTEGER NOT NULL DEFAULT 30
  );

  CREATE INDEX IF NOT EXISTS windows_tenant_idx ON windows (tenant_id);

  CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id        TEXT NOT NULL,
    contact_name     TEXT NOT NULL DEFAULT '',
    contact_email    TEXT NOT NULL DEFAULT '',
    contact_phone    TEXT NOT NULL DEFAULT '',
    start_at         TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 30,
    status           TEXT NOT NULL DEFAULT 'booked',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS appointments_tenant_idx ON appointments (tenant_id);
  CREATE INDEX IF NOT EXISTS appointments_start_idx ON appointments (tenant_id, start_at);
`;

function tenantFromRow(row) {
  return row ? { id: row.id, name: row.name, passcode: row.passcode, created_at: row.created_at } : null;
}

function windowFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    weekday: Number(row.weekday),
    start_minutes: Number(row.start_minutes),
    end_minutes: Number(row.end_minutes),
    slot_minutes: Number(row.slot_minutes),
  };
}

function appointmentFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    contact_name: row.contact_name,
    contact_email: row.contact_email,
    contact_phone: row.contact_phone,
    start_at: row.start_at,
    duration_minutes: Number(row.duration_minutes),
    status: row.status,
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

    listWindows: db.prepare('SELECT * FROM windows WHERE tenant_id = ? ORDER BY weekday, start_minutes'),
    insertWindow: db.prepare(
      'INSERT INTO windows (tenant_id, weekday, start_minutes, end_minutes, slot_minutes) VALUES (?, ?, ?, ?, ?)',
    ),
    deleteWindow: db.prepare('DELETE FROM windows WHERE tenant_id = ? AND id = ?'),

    listAppointments: db.prepare('SELECT * FROM appointments WHERE tenant_id = ? ORDER BY start_at'),
    listAppointmentsBetween: db.prepare(
      'SELECT * FROM appointments WHERE tenant_id = ? AND start_at >= ? AND start_at < ? ORDER BY start_at',
    ),
    getAppointment: db.prepare('SELECT * FROM appointments WHERE tenant_id = ? AND id = ?'),
    insertAppointment: db.prepare(
      `INSERT INTO appointments
         (tenant_id, contact_name, contact_email, contact_phone, start_at, duration_minutes, status, notes, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ),
    updateAppointmentStatus: db.prepare(
      'UPDATE appointments SET status = ?, updated_at = ? WHERE tenant_id = ? AND id = ?',
    ),
    deleteAppointment: db.prepare('DELETE FROM appointments WHERE tenant_id = ? AND id = ?'),
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

    listWindows(tenantId) {
      return stmt.listWindows.all(tenantId).map(windowFromRow);
    },

    insertWindow(tenantId, w) {
      const result = stmt.insertWindow.run(tenantId, w.weekday, w.start_minutes, w.end_minutes, w.slot_minutes);
      return windowFromRow(
        db.prepare('SELECT * FROM windows WHERE rowid = ?').get(Number(result.lastInsertRowid)),
      );
    },

    deleteWindow(tenantId, id) {
      return stmt.deleteWindow.run(tenantId, id).changes > 0;
    },

    listAppointments(tenantId) {
      return stmt.listAppointments.all(tenantId).map(appointmentFromRow);
    },

    listAppointmentsBetween(tenantId, startIso, endIso) {
      return stmt.listAppointmentsBetween.all(tenantId, startIso, endIso).map(appointmentFromRow);
    },

    getAppointment(tenantId, id) {
      return appointmentFromRow(stmt.getAppointment.get(tenantId, id));
    },

    insertAppointment(tenantId, appt) {
      const stamp = now();
      const result = stmt.insertAppointment.run(
        tenantId,
        appt.contact_name ?? '',
        appt.contact_email ?? '',
        appt.contact_phone ?? '',
        appt.start_at,
        appt.duration_minutes ?? 30,
        appt.status ?? 'booked',
        appt.notes ?? '',
        stamp,
        stamp,
      );
      return this.getAppointment(tenantId, Number(result.lastInsertRowid));
    },

    setAppointmentStatus(tenantId, id, status) {
      stmt.updateAppointmentStatus.run(status, now(), tenantId, id);
      return this.getAppointment(tenantId, id);
    },

    deleteAppointment(tenantId, id) {
      return stmt.deleteAppointment.run(tenantId, id).changes > 0;
    },
  };
}
