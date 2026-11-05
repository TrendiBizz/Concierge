// Concierge CRM dashboard. Vanilla ES module, no dependencies. All
// user-supplied text is inserted with textContent (never innerHTML).

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

const state = { tenant: null, stages: [], contacts: [], opportunities: [], view: 'contacts', search: '' };

function contactById(id) {
  return state.contacts.find((c) => c.id === id);
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
        h('p', { class: 'muted', text: 'CRM: contacts and pipeline' }),
        h('div', {}, h('label', { class: 'field', text: 'Passcode' }), input, message),
        h('button', { class: 'btn primary', onClick: submit, text: 'Sign in' }),
      ),
    ),
  );
  input.focus();
}

// ---------------------------------------------------------------- contacts view

function contactsView() {
  const search = h('input', {
    placeholder: 'Search contacts...',
    value: state.search,
    onInput: async (e) => {
      state.search = e.target.value;
      await refreshContacts();
      renderApp();
    },
  });
  const addForm = contactForm(null, async (data) => {
    await api('POST', '/api/contacts', data);
    await refreshContacts();
    toast('Contact added.');
    renderApp();
  });

  return h(
    'div',
    {},
    h('div', { class: 'row spread' }, h('h2', { text: 'Contacts' }), search),
    h(
      'table',
      {},
      h(
        'thead',
        {},
        h('tr', {}, h('th', { text: 'Name' }), h('th', { text: 'Email' }), h('th', { text: 'Phone' }), h('th', { text: 'Tags' }), h('th', {})),
      ),
      h(
        'tbody',
        {},
        state.contacts.map((c) =>
          h(
            'tr',
            {},
            h('td', { text: c.name }),
            h('td', { text: c.email }),
            h('td', { text: c.phone }),
            h('td', {}, c.tags.map((t) => h('span', { class: 'tag', text: t }))),
            h(
              'td',
              {},
              h('button', {
                class: 'btn small',
                text: 'Delete',
                onClick: async () => {
                  await api('DELETE', `/api/contacts/${c.id}`);
                  await refreshContacts();
                  renderApp();
                },
              }),
            ),
          ),
        ),
      ),
    ),
    h('h3', { style: 'margin-top:20px', text: 'Add a contact' }),
    addForm,
  );
}

function contactForm(existing, onSubmit) {
  const name = h('input', { value: existing ? existing.name : '', placeholder: 'Name' });
  const email = h('input', { value: existing ? existing.email : '', placeholder: 'Email' });
  const phone = h('input', { value: existing ? existing.phone : '', placeholder: 'Phone' });
  const tags = h('input', { value: existing ? existing.tags.join(', ') : '', placeholder: 'Tags (comma separated)' });
  const submit = async () => {
    if (!name.value.trim()) return toast('Name is required.', 'error');
    try {
      await onSubmit({
        name: name.value.trim(),
        email: email.value.trim(),
        phone: phone.value.trim(),
        tags: tags.value.split(',').map((t) => t.trim()).filter(Boolean),
      });
      name.value = '';
      email.value = '';
      phone.value = '';
      tags.value = '';
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  return h(
    'div',
    { class: 'card stack', style: 'max-width:420px' },
    name,
    email,
    phone,
    tags,
    h('button', { class: 'btn primary', onClick: submit, text: existing ? 'Save' : 'Add contact' }),
  );
}

// ---------------------------------------------------------------- pipeline board

function boardView() {
  const contactSelect = h(
    'select',
    {},
    h('option', { value: '', text: 'Choose a contact...' }),
    state.contacts.map((c) => h('option', { value: c.id, text: c.name })),
  );
  const title = h('input', { placeholder: 'Opportunity title' });
  const value = h('input', { type: 'number', placeholder: 'Value ($)', min: '0' });
  const addOpp = async () => {
    const contactId = Number(contactSelect.value);
    if (!contactId) return toast('Choose a contact first.', 'error');
    if (!title.value.trim()) return toast('Title is required.', 'error');
    await api('POST', '/api/opportunities', {
      contact_id: contactId,
      title: title.value.trim(),
      value: Number(value.value) || 0,
    });
    title.value = '';
    value.value = '';
    await refreshOpportunities();
    renderApp();
  };

  const columns = state.stages.map((stage) => {
    const opps = state.opportunities.filter((o) => o.stage === stage.name);
    const total = opps.reduce((sum, o) => sum + o.value, 0);
    return h(
      'div',
      { class: 'col' },
      h('h3', { text: stage.name }),
      h('p', { class: 'small muted', text: `${opps.length} · $${total.toLocaleString()}` }),
      opps.map((o) => {
        const contact = contactById(o.contact_id);
        const moveTo = h(
          'select',
          {
            onChange: async (e) => {
              await api('POST', `/api/opportunities/${o.id}/move`, { stage: e.target.value });
              await refreshOpportunities();
              renderApp();
            },
          },
          state.stages.map((s) => h('option', { value: s.name, selected: s.name === o.stage, text: s.name })),
        );
        return h(
          'div',
          { class: 'opp' },
          h('div', { text: o.title }),
          h('div', { class: 'muted', text: contact ? contact.name : 'Unknown contact' }),
          h('div', { class: 'value', text: `$${o.value.toLocaleString()}` }),
          moveTo,
          h('button', {
            class: 'btn small',
            style: 'margin-top:6px',
            text: 'Delete',
            onClick: async () => {
              await api('DELETE', `/api/opportunities/${o.id}`);
              await refreshOpportunities();
              renderApp();
            },
          }),
        );
      }),
    );
  });

  return h(
    'div',
    {},
    h('h2', { text: 'Pipeline' }),
    h(
      'div',
      { class: 'card row', style: 'margin-bottom:16px' },
      contactSelect,
      title,
      value,
      h('button', { class: 'btn primary', onClick: addOpp, text: 'Add opportunity' }),
    ),
    h('div', { class: 'board' }, columns),
  );
}

// ---------------------------------------------------------------- shell

async function refreshContacts() {
  const q = state.search ? `?q=${encodeURIComponent(state.search)}` : '';
  state.contacts = (await api('GET', `/api/contacts${q}`)).contacts;
}
async function refreshOpportunities() {
  state.opportunities = (await api('GET', '/api/opportunities')).opportunities;
}
async function refreshStages() {
  state.stages = (await api('GET', '/api/stages')).stages;
}

function renderApp() {
  const root = document.getElementById('app');
  const tab = (id, label) =>
    h('button', {
      class: `btn small${state.view === id ? ' active' : ''}`,
      text: label,
      onClick: () => {
        state.view = id;
        renderApp();
      },
    });
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
      h('nav', { class: 'tabs' }, tab('contacts', 'Contacts'), tab('pipeline', 'Pipeline')),
      state.view === 'contacts' ? contactsView() : boardView(),
    ),
  );
}

async function boot() {
  try {
    await Promise.all([refreshContacts(), refreshOpportunities(), refreshStages()]);
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
