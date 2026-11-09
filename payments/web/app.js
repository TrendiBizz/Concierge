// Concierge Payments dashboard. Vanilla ES module, no dependencies. All
// user-supplied text is inserted with textContent (never innerHTML).
// No real payment processing happens here -- "mark as paid" is a manual
// status change only. See README.

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'onClick') el.addEventListener('click', value);
    else if (key === 'onInput') el.addEventListener('input', value);
    else if (key === 'onChange') el.addEventListener('change', value);
    else if (key === 'onKeydown') el.addEventListener('keydown', value);
    else if (key === 'text') el.textContent = value;
    else if (key in el) el[key] = value;
    else el.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

let toastTimer;
function toast(message, cls = '') {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = `show ${cls}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = ''), 4000);
}

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let sessionToken = '';

async function api(method, path, body) {
  const init = { method, headers: {} };
  if (sessionToken) init.headers.Authorization = `Bearer ${sessionToken}`;
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    showLogin();
    throw new ApiError(401, 'Please sign in.');
  }
  if (!res.ok) throw new ApiError(res.status, data.error || `Request failed (${res.status})`);
  return data;
}

const money = (n) => `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const state = { tenant: null, invoices: [], statusFilter: '', draftItems: [{ description: '', quantity: 1, unit_price: 0 }] };

async function refreshInvoices() {
  const q = state.statusFilter ? `?status=${state.statusFilter}` : '';
  state.invoices = (await api('GET', `/api/invoices${q}`)).invoices;
}

// ---------------------------------------------------------------- login

function showLogin() {
  const root = document.getElementById('app');
  const input = h('input', { type: 'password', placeholder: 'Passcode', autocomplete: 'current-password' });
  const message = h('p', { class: 'small', style: 'color:var(--err);min-height:1.2em;margin:8px 0 0' });
  const submit = async () => {
    message.textContent = '';
    try {
      const data = await api('POST', '/api/login', { passcode: input.value });
      sessionToken = data.token;
      state.tenant = data.tenant;
      await boot();
    } catch (err) {
      message.textContent = err.message;
    }
  };
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submit();
  });
  root.replaceChildren(
    h(
      'div',
      { class: 'login' },
      h(
        'div',
        { class: 'card stack' },
        h('h1', { text: 'Concierge' }),
        h('p', { class: 'muted', text: 'Payments: invoicing' }),
        h('div', {}, h('label', { class: 'field', text: 'Passcode' }), input, message),
        h('button', { class: 'btn primary', onClick: submit, text: 'Sign in' }),
      ),
    ),
  );
  input.focus();
}

// ---------------------------------------------------------------- new invoice form

function itemsEditor() {
  const rows = state.draftItems.map((item, i) =>
    h(
      'div',
      { class: 'item-row' },
      h('input', {
        placeholder: 'Description',
        value: item.description,
        onInput: (e) => (state.draftItems[i].description = e.target.value),
      }),
      h('input', {
        type: 'number',
        min: '0.01',
        step: '1',
        value: item.quantity,
        onInput: (e) => (state.draftItems[i].quantity = Number(e.target.value)),
      }),
      h('input', {
        type: 'number',
        min: '0',
        step: '0.01',
        value: item.unit_price,
        onInput: (e) => (state.draftItems[i].unit_price = Number(e.target.value)),
      }),
      h('button', {
        class: 'btn small',
        text: '✕',
        onClick: () => {
          state.draftItems.splice(i, 1);
          if (state.draftItems.length === 0) state.draftItems.push({ description: '', quantity: 1, unit_price: 0 });
          renderApp();
        },
      }),
    ),
  );
  const subtotal = state.draftItems.reduce((s, it) => s + (Number(it.quantity) || 0) * (Number(it.unit_price) || 0), 0);
  return h(
    'div',
    {},
    h('div', { class: 'item-row small muted' }, h('div', { text: 'Description' }), h('div', { text: 'Qty' }), h('div', { text: 'Price' }), h('div', {})),
    rows,
    h('button', {
      class: 'btn small',
      text: '+ Add line',
      onClick: () => {
        state.draftItems.push({ description: '', quantity: 1, unit_price: 0 });
        renderApp();
      },
    }),
    h('div', { class: 'total-line', style: 'margin-top:8px' }, h('span', { text: 'Subtotal' }), h('span', { text: money(subtotal) })),
  );
}

function newInvoiceForm() {
  const name = h('input', { placeholder: 'Contact name' });
  const email = h('input', { placeholder: 'Email (optional)' });
  const dueDate = h('input', { type: 'date' });
  const taxRate = h('input', { type: 'number', min: '0', max: '100', step: '0.1', value: '0', placeholder: 'Tax %' });
  const notes = h('input', { placeholder: 'Notes (optional)' });

  const submit = async () => {
    if (!name.value.trim()) return toast('Contact name is required.', 'error');
    const items = state.draftItems.filter((it) => it.description.trim());
    if (items.length === 0) return toast('Add at least one line item.', 'error');
    try {
      await api('POST', '/api/invoices', {
        contact_name: name.value.trim(),
        contact_email: email.value.trim(),
        due_date: dueDate.value || null,
        tax_rate_percent: Number(taxRate.value) || 0,
        notes: notes.value.trim(),
        items,
      });
      toast('Invoice created.');
      state.draftItems = [{ description: '', quantity: 1, unit_price: 0 }];
      await refreshInvoices();
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  return h(
    'div',
    { class: 'card stack', style: 'max-width:520px' },
    h('h3', { text: 'New invoice' }),
    name,
    email,
    h('div', { class: 'row' }, h('label', { class: 'field', text: 'Due' }), dueDate, h('label', { class: 'field', text: 'Tax %' }), taxRate),
    notes,
    itemsEditor(),
    h('button', { class: 'btn primary', onClick: submit, text: 'Create invoice', style: 'margin-top:8px' }),
  );
}

// ---------------------------------------------------------------- list

function statusActions(invoice) {
  const move = async (status) => {
    try {
      await api('POST', `/api/invoices/${invoice.id}/status`, { status });
      await refreshInvoices();
      toast(`Marked ${status}.`);
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  if (invoice.status === 'draft') {
    return h(
      'div',
      { class: 'row' },
      h('button', { class: 'btn small', text: 'Mark sent', onClick: () => move('sent') }),
      h('button', { class: 'btn small', text: 'Void', onClick: () => move('void') }),
      h('button', {
        class: 'btn small',
        text: 'Delete',
        onClick: async () => {
          await api('DELETE', `/api/invoices/${invoice.id}`);
          await refreshInvoices();
          renderApp();
        },
      }),
    );
  }
  if (invoice.status === 'sent') {
    return h(
      'div',
      { class: 'row' },
      h('button', { class: 'btn small', text: 'Mark paid', onClick: () => move('paid') }),
      h('button', { class: 'btn small', text: 'Void', onClick: () => move('void') }),
    );
  }
  return null;
}

function invoicesList() {
  const filter = h(
    'select',
    {
      value: state.statusFilter,
      onChange: async (e) => {
        state.statusFilter = e.target.value;
        await refreshInvoices();
        renderApp();
      },
    },
    h('option', { value: '', text: 'All statuses' }),
    ['draft', 'sent', 'paid', 'void'].map((s) => h('option', { value: s, text: s })),
  );

  return h(
    'div',
    {},
    h('div', { class: 'row spread' }, h('h2', { text: 'Invoices' }), filter),
    h(
      'table',
      {},
      h(
        'thead',
        {},
        h(
          'tr',
          {},
          h('th', { text: '#' }),
          h('th', { text: 'Contact' }),
          h('th', { text: 'Total' }),
          h('th', { text: 'Due' }),
          h('th', { text: 'Status' }),
          h('th', {}),
        ),
      ),
      h(
        'tbody',
        {},
        state.invoices.map((inv) =>
          h(
            'tr',
            {},
            h('td', { text: inv.number }),
            h('td', { text: inv.contact_name }),
            h('td', { text: money(inv.total) }),
            h('td', { text: inv.due_date ? new Date(inv.due_date).toLocaleDateString() : '—' }),
            h('td', {}, h('span', { class: `badge ${inv.status}`, text: inv.status })),
            h('td', {}, statusActions(inv)),
          ),
        ),
      ),
    ),
  );
}

// ---------------------------------------------------------------- shell

function renderApp() {
  const root = document.getElementById('app');
  root.replaceChildren(
    h(
      'header',
      { class: 'topbar' },
      h('div', {}, h('b', { text: 'Concierge' }), h('span', { class: 'muted', text: ` · ${state.tenant.name}` })),
      h('button', {
        class: 'btn small',
        text: 'Sign out',
        onClick: () => {
          sessionToken = '';
          showLogin();
        },
      }),
    ),
    h(
      'main',
      {},
      h('div', { class: 'row', style: 'align-items:flex-start;gap:24px;flex-wrap:wrap' }, invoicesList(), newInvoiceForm()),
    ),
  );
}

async function boot() {
  try {
    await refreshInvoices();
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return;
    document.getElementById('app').replaceChildren(
      h('main', {}, h('div', { class: 'card', text: `Could not reach the server. ${err.message}` })),
    );
    return;
  }
  renderApp();
}

showLogin();
