// SQLite storage for Concierge Payments (built-in node:sqlite, no deps).
// Multi-tenant: every invoice and line item belongs to a tenant_id.
// No real payment processing lives here -- see README.

import { DatabaseSync } from 'node:sqlite';

const SCHEMA = `
  PRAGMA journal_mode = WAL;

  CREATE TABLE IF NOT EXISTS tenants (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    passcode   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS invoices (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id        TEXT NOT NULL,
    number           TEXT NOT NULL,
    contact_name     TEXT NOT NULL DEFAULT '',
    contact_email    TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'draft',
    due_date         TEXT,
    tax_rate_percent REAL NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
  );

  CREATE INDEX IF NOT EXISTS invoices_tenant_idx ON invoices (tenant_id);
  CREATE INDEX IF NOT EXISTS invoices_status_idx ON invoices (tenant_id, status);

  CREATE TABLE IF NOT EXISTS invoice_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id   TEXT NOT NULL,
    invoice_id  INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    quantity    REAL NOT NULL DEFAULT 1,
    unit_price  REAL NOT NULL DEFAULT 0,
    position    INTEGER NOT NULL DEFAULT 0
  );

  CREATE INDEX IF NOT EXISTS invoice_items_invoice_idx ON invoice_items (tenant_id, invoice_id);

  -- Per-tenant sequential invoice numbering (INV-0001, INV-0002, ...).
  -- Never reused, even if an invoice is later deleted.
  CREATE TABLE IF NOT EXISTS invoice_seq (
    tenant_id TEXT PRIMARY KEY,
    next      INTEGER NOT NULL DEFAULT 1
  );
`;

function tenantFromRow(row) {
  return row ? { id: row.id, name: row.name, passcode: row.passcode, created_at: row.created_at } : null;
}

function itemFromRow(row) {
  if (!row) return null;
  return {
    id: Number(row.id),
    invoice_id: Number(row.invoice_id),
    description: row.description,
    quantity: Number(row.quantity),
    unit_price: Number(row.unit_price),
    position: Number(row.position),
  };
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

function withTotals(row, items) {
  const subtotal = items.reduce((sum, it) => sum + it.quantity * it.unit_price, 0);
  const tax = subtotal * (Number(row.tax_rate_percent) / 100);
  return {
    id: Number(row.id),
    tenant_id: row.tenant_id,
    number: row.number,
    contact_name: row.contact_name,
    contact_email: row.contact_email,
    status: row.status,
    due_date: row.due_date,
    tax_rate_percent: Number(row.tax_rate_percent),
    notes: row.notes,
    items,
    subtotal: round2(subtotal),
    tax: round2(tax),
    total: round2(subtotal + tax),
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

    nextSeq: db.prepare('SELECT next FROM invoice_seq WHERE tenant_id = ?'),
    insertSeq: db.prepare('INSERT INTO invoice_seq (tenant_id, next) VALUES (?, 2)'),
    bumpSeq: db.prepare('UPDATE invoice_seq SET next = next + 1 WHERE tenant_id = ?'),

    listInvoices: db.prepare('SELECT * FROM invoices WHERE tenant_id = ? ORDER BY created_at DESC'),
    getInvoiceRow: db.prepare('SELECT * FROM invoices WHERE tenant_id = ? AND id = ?'),
    insertInvoice: db.prepare(
      `INSERT INTO invoices (tenant_id, number, contact_name, contact_email, status, due_date, tax_rate_percent, notes, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)`,
    ),
    updateInvoice: db.prepare(
      `UPDATE invoices SET contact_name = ?, contact_email = ?, due_date = ?, tax_rate_percent = ?, notes = ?, updated_at = ?
       WHERE tenant_id = ? AND id = ?`,
    ),
    updateInvoiceStatus: db.prepare('UPDATE invoices SET status = ?, updated_at = ? WHERE tenant_id = ? AND id = ?'),
    deleteInvoice: db.prepare('DELETE FROM invoices WHERE tenant_id = ? AND id = ?'),

    listItems: db.prepare('SELECT * FROM invoice_items WHERE tenant_id = ? AND invoice_id = ? ORDER BY position'),
    deleteItems: db.prepare('DELETE FROM invoice_items WHERE tenant_id = ? AND invoice_id = ?'),
    insertItem: db.prepare(
      'INSERT INTO invoice_items (tenant_id, invoice_id, description, quantity, unit_price, position) VALUES (?, ?, ?, ?, ?, ?)',
    ),
  };

  const now = () => new Date().toISOString();

  function nextInvoiceNumber(tenantId) {
    const row = stmt.nextSeq.get(tenantId);
    if (!row) {
      stmt.insertSeq.run(tenantId);
      return 'INV-0001';
    }
    stmt.bumpSeq.run(tenantId);
    return `INV-${String(row.next).padStart(4, '0')}`;
  }

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

    getInvoice(tenantId, id) {
      const row = stmt.getInvoiceRow.get(tenantId, id);
      if (!row) return null;
      return withTotals(row, stmt.listItems.all(tenantId, id).map(itemFromRow));
    },

    listInvoices(tenantId) {
      return stmt.listInvoices
        .all(tenantId)
        .map((row) => withTotals(row, stmt.listItems.all(tenantId, row.id).map(itemFromRow)));
    },

    // items: [{description, quantity, unit_price}]
    insertInvoice(tenantId, invoice, items) {
      const stamp = now();
      const number = nextInvoiceNumber(tenantId);
      const result = stmt.insertInvoice.run(
        tenantId,
        number,
        invoice.contact_name ?? '',
        invoice.contact_email ?? '',
        invoice.due_date ?? null,
        invoice.tax_rate_percent ?? 0,
        invoice.notes ?? '',
        stamp,
        stamp,
      );
      const id = Number(result.lastInsertRowid);
      this.replaceItems(tenantId, id, items);
      return this.getInvoice(tenantId, id);
    },

    replaceItems(tenantId, invoiceId, items) {
      stmt.deleteItems.run(tenantId, invoiceId);
      (items || []).forEach((it, i) => {
        stmt.insertItem.run(tenantId, invoiceId, it.description ?? '', it.quantity ?? 1, it.unit_price ?? 0, i);
      });
    },

    saveInvoice(tenantId, id, invoice, items) {
      stmt.updateInvoice.run(
        invoice.contact_name,
        invoice.contact_email,
        invoice.due_date ?? null,
        invoice.tax_rate_percent,
        invoice.notes,
        now(),
        tenantId,
        id,
      );
      if (items) this.replaceItems(tenantId, id, items);
      return this.getInvoice(tenantId, id);
    },

    setInvoiceStatus(tenantId, id, status) {
      stmt.updateInvoiceStatus.run(status, now(), tenantId, id);
      return this.getInvoice(tenantId, id);
    },

    deleteInvoice(tenantId, id) {
      stmt.deleteItems.run(tenantId, id);
      return stmt.deleteInvoice.run(tenantId, id).changes > 0;
    },
  };
}
