// Concierge Sites dashboard. Vanilla ES module, no dependencies. All
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

const state = { tenant: null, pages: [], leads: [], view: 'pages', editingBlocks: null, editingPageId: null };

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
        h('p', { class: 'muted', text: 'Sites: pages and leads' }),
        h('div', {}, h('label', { class: 'field', text: 'Passcode' }), input, message),
        h('button', { class: 'btn primary', onClick: submit, text: 'Sign in' }),
      ),
    ),
  );
  input.focus();
}

// ---------------------------------------------------------------- block editor

const BLOCK_LABELS = { heading: 'Heading', paragraph: 'Paragraph', image: 'Image', button: 'Button', form: 'Lead form' };

function blockFields(block, onChange) {
  const set = (patch) => onChange({ ...block, content: { ...block.content, ...patch } });
  switch (block.type) {
    case 'heading':
      return [h('input', { placeholder: 'Heading text', value: block.content.text || '', onInput: (e) => set({ text: e.target.value }) })];
    case 'paragraph':
      return [h('textarea', { placeholder: 'Paragraph text', rows: 3, value: block.content.text || '', onInput: (e) => set({ text: e.target.value }) })];
    case 'image':
      return [
        h('input', { placeholder: 'Image URL', value: block.content.url || '', onInput: (e) => set({ url: e.target.value }) }),
        h('input', { placeholder: 'Alt text', value: block.content.alt || '', onInput: (e) => set({ alt: e.target.value }) }),
      ];
    case 'button':
      return [
        h('input', { placeholder: 'Button text', value: block.content.text || '', onInput: (e) => set({ text: e.target.value }) }),
        h('input', { placeholder: 'Link (https://...)', value: block.content.link || '', onInput: (e) => set({ link: e.target.value }) }),
      ];
    case 'form':
      return [h('p', { class: 'small muted', text: 'Captures name + email. Submissions show up under Leads.' })];
    default:
      return [];
  }
}

function blockEditor() {
  const blocks = state.editingBlocks;
  const addType = h('select', {}, Object.entries(BLOCK_LABELS).map(([v, label]) => h('option', { value: v, text: label })));
  const list = blocks.map((b, i) =>
    h(
      'div',
      { class: 'block-row' },
      h(
        'div',
        { class: 'row spread' },
        h('b', { class: 'small', text: BLOCK_LABELS[b.type] }),
        h('div', { class: 'row' }, [
          i > 0 ? h('button', { class: 'btn small', text: '↑', onClick: () => { [blocks[i - 1], blocks[i]] = [blocks[i], blocks[i - 1]]; renderEditorModal(); } }) : null,
          i < blocks.length - 1 ? h('button', { class: 'btn small', text: '↓', onClick: () => { [blocks[i + 1], blocks[i]] = [blocks[i], blocks[i + 1]]; renderEditorModal(); } }) : null,
          h('button', { class: 'btn small', text: 'Remove', onClick: () => { blocks.splice(i, 1); renderEditorModal(); } }),
        ]),
      ),
      ...blockFields(b, (next) => (blocks[i] = next)),
    ),
  );
  return h(
    'div',
    { class: 'stack' },
    list.length ? list : h('p', { class: 'muted small', text: 'No blocks yet.' }),
    h(
      'div',
      { class: 'row' },
      addType,
      h('button', {
        class: 'btn small',
        text: '+ Add block',
        onClick: () => {
          const type = addType.value;
          blocks.push({ type, content: type === 'form' ? { fields: ['name', 'email'], submit_label: 'Submit' } : {} });
          renderEditorModal();
        },
      }),
    ),
    h('button', {
      class: 'btn primary',
      text: 'Save blocks',
      onClick: async () => {
        try {
          await api('PUT', `/api/pages/${state.editingPageId}`, { blocks });
          toast('Saved.');
          await refreshPages();
          closeModal();
          renderApp();
        } catch (err) {
          toast(err.message, 'error');
        }
      },
    }),
  );
}

function renderEditorModal() {
  openModal('Edit page content', blockEditor());
}

// ---------------------------------------------------------------- pages view

function pagesView() {
  const newSlug = h('input', { placeholder: 'url-slug' });
  const newTitle = h('input', { placeholder: 'Title' });
  const create = async () => {
    if (!newSlug.value.trim()) return toast('Slug is required.', 'error');
    try {
      await api('POST', '/api/pages', { slug: newSlug.value.trim(), title: newTitle.value.trim() });
      newSlug.value = '';
      newTitle.value = '';
      await refreshPages();
      toast('Page created.');
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  return h(
    'div',
    {},
    h('h2', { text: 'Pages' }),
    h(
      'table',
      {},
      h('thead', {}, h('tr', {}, h('th', { text: 'Title' }), h('th', { text: 'Slug' }), h('th', { text: 'Status' }), h('th', {}))),
      h(
        'tbody',
        {},
        state.pages.map((p) =>
          h(
            'tr',
            {},
            h('td', { text: p.title }),
            h('td', { text: p.slug }),
            h('td', {}, h('span', { class: `badge ${p.status}`, text: p.status })),
            h(
              'td',
              { class: 'row' },
              h('a', { class: 'btn small', href: `/site/${state.tenant.id}/${p.slug}`, target: '_blank', rel: 'noopener', text: 'View' }),
              h('button', {
                class: 'btn small',
                text: 'Edit',
                onClick: async () => {
                  const full = (await api('GET', `/api/pages/${p.id}`)).page;
                  state.editingPageId = p.id;
                  state.editingBlocks = full.blocks.map((b) => ({ type: b.type, content: { ...b.content } }));
                  renderEditorModal();
                },
              }),
              h('button', {
                class: 'btn small',
                text: p.status === 'published' ? 'Unpublish' : 'Publish',
                onClick: async () => {
                  await api('POST', `/api/pages/${p.id}/status`, { status: p.status === 'published' ? 'draft' : 'published' });
                  await refreshPages();
                  renderApp();
                },
              }),
              h('button', {
                class: 'btn small',
                text: 'Delete',
                onClick: async () => {
                  await api('DELETE', `/api/pages/${p.id}`);
                  await refreshPages();
                  renderApp();
                },
              }),
            ),
          ),
        ),
      ),
    ),
    h('h3', { style: 'margin-top:20px', text: 'New page' }),
    h('div', { class: 'card row', style: 'max-width:500px' }, newSlug, newTitle, h('button', { class: 'btn primary', onClick: create, text: 'Create' })),
  );
}

// ---------------------------------------------------------------- leads view

function leadsView() {
  return h(
    'div',
    {},
    h('h2', { text: 'Leads' }),
    state.leads.length === 0
      ? h('p', { class: 'muted', text: 'No leads yet.' })
      : h(
          'table',
          {},
          h('thead', {}, h('tr', {}, h('th', { text: 'When' }), h('th', { text: 'Page' }), h('th', { text: 'Details' }))),
          h(
            'tbody',
            {},
            state.leads.map((l) => {
              const page = state.pages.find((p) => p.id === l.page_id);
              return h(
                'tr',
                {},
                h('td', { text: new Date(l.created_at).toLocaleString() }),
                h('td', { text: page ? page.title : `#${l.page_id}` }),
                h('td', { text: Object.entries(l.data).map(([k, v]) => `${k}: ${v}`).join(', ') }),
              );
            }),
          ),
        ),
  );
}

// ---------------------------------------------------------------- shell

async function refreshPages() {
  state.pages = (await api('GET', '/api/pages')).pages;
}
async function refreshLeads() {
  state.leads = (await api('GET', '/api/leads')).leads;
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
      h('nav', { class: 'row', style: 'margin-bottom:16px' }, tab('pages', 'Pages'), tab('leads', 'Leads')),
      state.view === 'pages' ? pagesView() : leadsView(),
    ),
  );
}

async function boot() {
  try {
    await Promise.all([refreshPages(), refreshLeads()]);
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
