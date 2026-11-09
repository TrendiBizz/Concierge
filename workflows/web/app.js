// Concierge Workflows dashboard. Vanilla ES module, no dependencies. All
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

const state = { tenant: null, view: 'workflows', workflows: [], runs: [], draftActions: [] };

let activeModal = null;
function closeModal() {
  if (activeModal) {
    activeModal.remove();
    activeModal = null;
  }
}
function openModal(title, content) {
  closeModal();
  const close = h('button', { class: 'btn small', onClick: closeModal, text: 'Close' });
  const backdrop = h(
    'div',
    { class: 'backdrop', onClick: (e) => e.target === backdrop && closeModal() },
    h('div', { class: 'modal' }, h('div', { class: 'row spread' }, h('h3', { text: title }), close), content),
  );
  document.body.append(backdrop);
  activeModal = backdrop;
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
        h('p', { class: 'muted', text: 'Workflows: automations' }),
        h('div', {}, h('label', { class: 'field', text: 'Passcode' }), input, message),
        h('button', { class: 'btn primary', onClick: submit, text: 'Sign in' }),
      ),
    ),
  );
  input.focus();
}

// ---------------------------------------------------------------- new/edit workflow

function actionEditor() {
  const actions = state.draftActions;
  const addType = h('select', {}, h('option', { value: 'log', text: 'Log' }), h('option', { value: 'webhook', text: 'Webhook' }));
  const rows = actions.map((a, i) =>
    h(
      'div',
      { class: 'action-row' },
      h('div', { class: 'row spread' }, h('b', { class: 'small', text: a.type === 'log' ? 'Log' : 'Webhook' }), h('button', { class: 'btn small', text: 'Remove', onClick: () => { actions.splice(i, 1); renderNewWorkflowModal(); } })),
      a.type === 'log'
        ? h('input', { placeholder: 'Message, use {{field}} for event data', value: a.message || '', onInput: (e) => (a.message = e.target.value) })
        : h('input', { placeholder: 'https://your-url/hook', value: a.url || '', onInput: (e) => (a.url = e.target.value) }),
    ),
  );
  return h(
    'div',
    { class: 'stack' },
    rows.length ? rows : h('p', { class: 'muted small', text: 'No actions yet.' }),
    h(
      'div',
      { class: 'row' },
      addType,
      h('button', {
        class: 'btn small',
        text: '+ Add action',
        onClick: () => {
          actions.push(addType.value === 'log' ? { type: 'log', message: '' } : { type: 'webhook', url: '' });
          renderNewWorkflowModal();
        },
      }),
    ),
  );
}

function newWorkflowModal(existing) {
  const name = h('input', { placeholder: 'Workflow name', value: existing ? existing.name : '' });
  const eventType = h('input', { placeholder: 'Trigger event, e.g. lead.created', value: existing ? existing.event_type : '' });
  state.draftActions = existing ? existing.actions.map((a) => ({ ...a })) : [];

  const save = async () => {
    if (!name.value.trim()) return toast('Name is required.', 'error');
    if (!eventType.value.trim()) return toast('Trigger event is required.', 'error');
    try {
      const payload = { name: name.value.trim(), event_type: eventType.value.trim(), actions: state.draftActions };
      if (existing) await api('PUT', `/api/workflows/${existing.id}`, payload);
      else await api('POST', '/api/workflows', payload);
      toast(existing ? 'Saved.' : 'Workflow created.');
      await refreshWorkflows();
      closeModal();
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  return h(
    'div',
    { class: 'stack' },
    name,
    eventType,
    h('h3', { style: 'margin:12px 0 0', text: 'Actions' }),
    actionEditor(),
    h('button', { class: 'btn primary', onClick: save, text: existing ? 'Save workflow' : 'Create workflow' }),
  );
}

function renderNewWorkflowModal(existing) {
  openModal(existing ? 'Edit workflow' : 'New workflow', newWorkflowModal(existing));
}

// ---------------------------------------------------------------- test-event sender

function testEventForm() {
  const type = h('input', { placeholder: 'Event type, e.g. lead.created' });
  const data = h('textarea', { placeholder: '{"name":"Jane","email":"jane@example.com"}', rows: 2 });
  const send = async () => {
    if (!type.value.trim()) return toast('Event type is required.', 'error');
    let parsed = {};
    try {
      parsed = data.value.trim() ? JSON.parse(data.value) : {};
    } catch {
      return toast('Data must be valid JSON.', 'error');
    }
    try {
      const result = await api('POST', '/api/events', { type: type.value.trim(), data: parsed });
      toast(`${result.matched} workflow(s) fired.`);
      await refreshRuns();
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };
  return h(
    'div',
    { class: 'card stack', style: 'max-width:420px' },
    h('h3', { text: 'Send a test event' }),
    type,
    data,
    h('button', { class: 'btn primary', onClick: send, text: 'Fire event' }),
  );
}

// ---------------------------------------------------------------- views

function workflowsView() {
  return h(
    'div',
    {},
    h(
      'div',
      { class: 'row spread' },
      h('h2', { text: 'Workflows' }),
      h('button', { class: 'btn primary', text: '+ New workflow', onClick: () => renderNewWorkflowModal() }),
    ),
    h(
      'table',
      {},
      h('thead', {}, h('tr', {}, h('th', { text: 'Name' }), h('th', { text: 'Trigger' }), h('th', { text: 'Actions' }), h('th', { text: 'Status' }), h('th', {}))),
      h(
        'tbody',
        {},
        state.workflows.map((wf) =>
          h(
            'tr',
            {},
            h('td', { text: wf.name }),
            h('td', { text: wf.event_type }),
            h('td', { text: `${wf.actions.length}` }),
            h('td', {}, h('span', { class: `badge ${wf.enabled ? 'on' : 'off'}`, text: wf.enabled ? 'On' : 'Off' })),
            h(
              'td',
              { class: 'row' },
              h('button', { class: 'btn small', text: 'Edit', onClick: () => renderNewWorkflowModal(wf) }),
              h('button', {
                class: 'btn small',
                text: wf.enabled ? 'Turn off' : 'Turn on',
                onClick: async () => {
                  await api('PUT', `/api/workflows/${wf.id}`, { enabled: !wf.enabled });
                  await refreshWorkflows();
                  renderApp();
                },
              }),
              h('button', {
                class: 'btn small',
                text: 'Delete',
                onClick: async () => {
                  await api('DELETE', `/api/workflows/${wf.id}`);
                  await refreshWorkflows();
                  renderApp();
                },
              }),
            ),
          ),
        ),
      ),
    ),
    h('div', { style: 'margin-top:20px' }, testEventForm()),
  );
}

function runsView() {
  return h(
    'div',
    {},
    h('h2', { text: 'Run history' }),
    state.runs.length === 0
      ? h('p', { class: 'muted', text: 'No runs yet.' })
      : h(
          'table',
          {},
          h('thead', {}, h('tr', {}, h('th', { text: 'When' }), h('th', { text: 'Event' }), h('th', { text: 'Status' }), h('th', { text: 'Results' }))),
          h(
            'tbody',
            {},
            state.runs.map((r) =>
              h(
                'tr',
                {},
                h('td', { text: new Date(r.created_at).toLocaleString() }),
                h('td', { text: r.event_type }),
                h('td', {}, h('span', { class: `badge ${r.ok ? 'ok' : 'fail'}`, text: r.ok ? 'ok' : 'failed' })),
                h('td', { class: 'small', text: r.results.map((x) => `${x.type}: ${x.detail}`).join(' | ') }),
              ),
            ),
          ),
        ),
  );
}

// ---------------------------------------------------------------- shell

async function refreshWorkflows() {
  state.workflows = (await api('GET', '/api/workflows')).workflows;
}
async function refreshRuns() {
  state.runs = (await api('GET', '/api/runs')).runs;
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
      h('nav', { class: 'row', style: 'margin-bottom:16px' }, tab('workflows', 'Workflows'), tab('runs', 'Run history')),
      state.view === 'workflows' ? workflowsView() : runsView(),
    ),
  );
}

async function boot() {
  try {
    await Promise.all([refreshWorkflows(), refreshRuns()]);
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
