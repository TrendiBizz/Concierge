// SocialSync dashboard for Pukeko Construction.
// Vanilla ES module, no dependencies. All user-supplied text is inserted with
// textContent (never innerHTML), so posts cannot inject markup.

// ---------------------------------------------------------------- icons (trusted constants)

const ICONS = {
  linkedin:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" aria-hidden="true"><path fill="currentColor" d="M416 32H31.9C14.3 32 0 46.5 0 64.3v383.4C0 465.5 14.3 480 31.9 480H416c17.6 0 32-14.5 32-32.3V64.3c0-17.8-14.4-32.3-32-32.3zM135.4 416H69V202.2h66.5V416zm-33.2-243c-21.3 0-38.5-17.3-38.5-38.5S80.9 96 102.2 96c21.2 0 38.5 17.3 38.5 38.5 0 21.3-17.2 38.5-38.5 38.5zm282.1 243h-66.4V312c0-24.8-.5-56.7-34.5-56.7-34.6 0-39.9 27-39.9 54.9V416h-66.4V202.2h63.7v29.2h.9c8.9-16.8 30.6-34.5 62.9-34.5 67.2 0 79.7 44.3 79.7 101.9V416z"/></svg>',
  facebook:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" aria-hidden="true"><path fill="currentColor" d="M512 256C512 114.6 397.4 0 256 0S0 114.6 0 256C0 376.6 85.8 478.5 200 506.8V334H160v-78h40v-54.4c0-71.8 42.8-111.6 108.2-111.6 31.3 0 64.2 5.6 64.2 5.6v70.4h-36.2c-35.6 0-46.8 22.2-46.8 44.8V256h80l-13 78H289v172.8c114.2-28.3 200-130.2 200-250.8"/></svg>',
  instagram:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" aria-hidden="true"><path fill="currentColor" d="M224.1 141c-63.6 0-114.9 51.3-114.9 114.9s51.3 114.9 114.9 114.9S339 319.5 339 255.9 287.7 141 224.1 141zm0 189.6c-41.1 0-74.7-33.5-74.7-74.7s33.5-74.7 74.7-74.7 74.7 33.5 74.7 74.7-33.6 74.7-74.7 74.7zm146.4-194.3c0 14.9-12 26.8-26.8 26.8-14.9 0-26.8-12-26.8-26.8s12-26.8 26.8-26.8 26.8 12 26.8 26.8zm76.1 27.2c-1.7-35.9-9.9-67.7-36.2-93.9-26.2-26.2-58-34.4-93.9-36.2-37-2.1-147.9-2.1-184.9 0-35.8 1.7-67.6 9.9-93.9 36.1s-34.4 58-36.2 93.9c-2.1 37-2.1 147.9 0 184.9 1.7 35.9 9.9 67.7 36.2 93.9s58 34.4 93.9 36.2c37 2.1 147.9 2.1 184.9 0 35.9-1.7 67.7-9.9 93.9-36.2 26.2-26.2 34.4-58 36.2-93.9 2.1-37 2.1-147.8 0-184.8zM398.8 388c-7.8 19.6-22.9 34.7-42.6 42.6-29.5 11.7-99.5 9-132.1 9s-102.7 2.6-132.1-9c-19.6-7.8-34.7-22.9-42.6-42.6-11.7-29.5-9-99.5-9-132.1s-2.6-102.7 9-132.1c7.8-19.6 22.9-34.7 42.6-42.6 29.5-11.7 99.5-9 132.1-9s102.7-2.6 132.1 9c19.6 7.8 34.7 22.9 42.6 42.6 11.7 29.5 9 99.5 9 132.1s2.7 102.7-9 132.1z"/></svg>',
  twitter:
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" aria-hidden="true"><path fill="currentColor" d="M389.2 48h70.6L305.6 224.2 487 464H345L233.7 318.6 106.5 464H35.8L200.7 275.5 26.8 48H172.4L272.9 180.9 389.2 48zM364.4 421.8h39.1L151.1 88h-42L364.4 421.8z"/></svg>',
};

// ---------------------------------------------------------------- small helpers

const BOOLEAN_PROPS = new Set(['checked', 'disabled', 'selected', 'multiple', 'required']);

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'value') el.value = value;
    else if (BOOLEAN_PROPS.has(key)) el[key] = Boolean(value);
    else el.setAttribute(key, value === true ? '' : String(value));
  }
  append(el, children);
  return el;
}

function icon(id) {
  const span = document.createElement('span');
  span.className = `pf-icon pf-${id}`;
  span.innerHTML = ICONS[id] || '';
  return span;
}

const pad = (n) => String(n).padStart(2, '0');
const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);

function toLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return `${dayKey(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtDateTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-NZ', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('en-NZ', { hour: 'numeric', minute: '2-digit' });
}

function excerpt(text, max) {
  const flat = String(text || '').replace(/\s+/g, ' ').trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat || '(no text)';
}

let toastTimer;
function toast(message, kind = '') {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = `show ${kind}`.trim();
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.className = '';
  }, 4000);
}

class ApiError extends Error {
  constructor(status, message, data) {
    super(message);
    this.status = status;
    this.data = data || {};
  }
}

// Kept in memory, not localStorage: embedded inside Concierge's GHL iframe
// this is a different origin than the dashboard it sits in, and a cookie
// set there does not reliably come back on later requests without HTTPS
// (see server.js tenantCookies). The token from /api/tenant/bootstrap or
// /api/login is sent back explicitly as a Bearer header instead.
let sessionToken = '';

async function api(method, path, body, raw) {
  const init = { method, credentials: 'same-origin', headers: {} };
  if (sessionToken) init.headers.Authorization = `Bearer ${sessionToken}`;
  if (raw) {
    init.body = raw.blob;
    init.headers['Content-Type'] = raw.type;
  } else if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const res = await fetch(path, init);
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (res.status === 401 && path !== '/api/login') {
    showLogin();
    throw new ApiError(401, 'Please sign in.', data);
  }
  if (!res.ok) throw new ApiError(res.status, data.error || `Request failed (${res.status})`, data);
  return data;
}

function explain(err) {
  if (err instanceof ApiError && Array.isArray(err.data.problems) && err.data.problems.length) {
    return `${err.message} ${err.data.problems.join(' ')}`;
  }
  return err && err.message ? err.message : 'Something went wrong.';
}

// ---------------------------------------------------------------- state

const state = {
  rules: null,
  posts: [],
  media: [],
  view: 'compose',
  calMonth: startOfMonth(new Date()),
  filter: 'all',
  projectFilter: '',
  channels: [],
  channelPlatforms: [],
  draft: blankDraft(),
};

function blankDraft() {
  return {
    id: null,
    status: 'draft',
    content: '',
    link: '',
    hashtags: '',
    platforms: [],
    media_ids: [],
    when: '',
  };
}

const isDue = (post) => post.status === 'scheduled' && Date.parse(post.scheduled_at) <= Date.now();
const mediaById = (id) => state.media.find((m) => m.id === id);
// <img src>/<a href> are plain browser requests, not fetch() calls, so they
// never carry the Authorization header api() adds. The token travels as a
// query param instead (server.js accepts it there for exactly this).
const mediaSrc = (m) => `${m.url}${sessionToken ? `?token=${encodeURIComponent(sessionToken)}` : ''}`;
const platformLabel = (id) => (state.rules.platforms[id] ? state.rules.platforms[id].label : id);

function postText(post) {
  return [post.content, post.link, post.hashtags]
    .map((s) => (s || '').trim())
    .filter(Boolean)
    .join('\n\n');
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = h('textarea', { style: 'position:fixed;opacity:0' });
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  toast('Copied. Paste it into the platform.');
}

async function refreshPosts() {
  state.posts = (await api('GET', '/api/posts')).posts;
}

async function refreshMedia() {
  state.media = (await api('GET', '/api/media')).media;
}

async function refreshChannels() {
  const data = await api('GET', '/api/channels');
  state.channels = data.channels;
  state.channelPlatforms = data.platforms;
}

// ---------------------------------------------------------------- modal

let activeModal = null;

function closeModal() {
  if (activeModal) {
    activeModal.remove();
    activeModal = null;
  }
}

function openModal(title, content, { wide = false } = {}) {
  closeModal();
  const close = h('button', { class: 'btn small ghost', 'aria-label': 'Close', onClick: closeModal, text: 'Close' });
  const backdrop = h(
    'div',
    {
      class: 'backdrop',
      onClick: (e) => {
        if (e.target === backdrop) closeModal();
      },
    },
    h(
      'div',
      { class: `modal${wide ? ' wide' : ''}`, role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('div', { class: 'row spread' }, h('h3', { text: title }), close),
      h('div', { style: 'margin-top:14px' }, content),
    ),
  );
  document.body.append(backdrop);
  activeModal = backdrop;
  close.focus();
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});

// ---------------------------------------------------------------- login

function showLogin() {
  closeModal();
  const root = document.getElementById('app');
  const input = h('input', {
    type: 'password',
    id: 'passcode',
    autocomplete: 'current-password',
    placeholder: 'Passcode',
    'aria-label': 'Passcode',
  });
  const message = h('p', { class: 'small', style: 'color:var(--err);min-height:1.2em;margin:8px 0 0' });
  const submit = async () => {
    message.textContent = '';
    try {
      const data = await api('POST', '/api/login', { passcode: input.value });
      sessionToken = data.token;
      await boot();
    } catch (err) {
      message.textContent = explain(err);
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
        h(
          'div',
          {},
          h('img', { class: 'logo', src: '/pukeko-logo.png', alt: 'Pukeko Construction' }),
          h('p', { class: 'muted', style: 'text-align:center;margin:8px 0 0', text: 'SocialSync: social media planner' }),
        ),
        h('div', {}, h('label', { class: 'field', for: 'passcode', text: 'Passcode' }), input, message),
        h('button', { class: 'btn primary', onClick: submit, text: 'Sign in' }),
      ),
    ),
  );
  input.focus();
}

// ---------------------------------------------------------------- shell

const VIEWS = [
  ['compose', 'Compose'],
  ['calendar', 'Calendar'],
  ['posts', 'Posts'],
  ['photos', 'Photos'],
  ['pages', 'Pages'],
];

function go(view) {
  state.view = view;
  renderApp();
}

function renderApp() {
  closeModal();
  const dueCount = state.posts.filter(isDue).length;
  const nav = h(
    'nav',
    { class: 'nav', 'aria-label': 'Sections' },
    VIEWS.map(([id, label]) =>
      h(
        'button',
        { 'aria-current': state.view === id ? 'page' : null, onClick: () => go(id) },
        label,
        id === 'posts' && dueCount > 0 ? h('span', { class: 'dot', text: String(dueCount), title: `${dueCount} due now` }) : null,
      ),
    ),
  );
  const logout = h('button', {
    class: 'btn small',
    text: 'Sign out',
    onClick: async () => {
      await api('POST', '/api/logout').catch(() => {});
      showLogin();
    },
  });
  const header = h(
    'header',
    { class: 'topbar' },
    h(
      'div',
      { class: 'topbar-inner' },
      h(
        'div',
        { class: 'brand-row' },
        h(
          'div',
          { class: 'brand' },
          h('img', { class: 'logo', src: '/pukeko-logo.png', alt: 'Pukeko Construction' }),
          h('span', { class: 'tool', text: 'SocialSync' }),
        ),
        logout,
      ),
      nav,
    ),
  );
  const main = h('main', { id: 'view' });
  document.getElementById('app').replaceChildren(header, main);
  const builders = {
    compose: composeView,
    calendar: calendarView,
    posts: postsView,
    photos: photosView,
    pages: pagesView,
  };
  main.append(builders[state.view]());
}

// ---------------------------------------------------------------- shared post actions

function editPost(post) {
  state.draft = {
    id: post.id,
    status: post.status,
    content: post.content,
    link: post.link,
    hashtags: post.hashtags,
    platforms: [...post.platforms],
    media_ids: [...post.media_ids],
    when: toLocalInput(post.scheduled_at),
  };
  go('compose');
}

async function changed() {
  await Promise.all([refreshPosts(), refreshMedia()]);
  renderApp();
}

function postActions(post) {
  const buttons = [];
  const postNow = postNowBox(post);
  if (postNow) buttons.push(postNow);
  const run = (fn) => async () => {
    try {
      await fn();
    } catch (err) {
      toast(explain(err), 'error');
    }
  };
  if (post.status !== 'posted') {
    buttons.push(h('button', { class: 'btn small', text: 'Edit', onClick: () => editPost(post) }));
  }
  buttons.push(h('button', { class: 'btn small', text: 'Copy text', onClick: () => copyText(postText(post)) }));
  if (post.status !== 'posted') {
    buttons.push(
      h('button', {
        class: 'btn small primary',
        text: 'Mark as posted',
        onClick: run(async () => {
          if (!window.confirm('Mark this as posted? Only do this once it is live on the platforms.')) return;
          await api('POST', `/api/posts/${post.id}/mark-posted`);
          toast('Marked as posted.');
          await changed();
        }),
      }),
    );
  }
  if (post.status === 'scheduled') {
    buttons.push(
      h('button', {
        class: 'btn small',
        text: 'Unschedule',
        onClick: run(async () => {
          await api('POST', `/api/posts/${post.id}/unschedule`);
          await changed();
        }),
      }),
    );
  }
  buttons.push(
    h('button', {
      class: 'btn small',
      text: 'Duplicate',
      onClick: run(async () => {
        const res = await api('POST', `/api/posts/${post.id}/duplicate`);
        await refreshPosts();
        toast('Copied to a new draft.');
        editPost(res.post);
      }),
    }),
  );
  buttons.push(
    h('button', {
      class: 'btn small danger',
      text: 'Delete',
      onClick: run(async () => {
        if (!window.confirm('Delete this post for good?')) return;
        await api('DELETE', `/api/posts/${post.id}`);
        await changed();
      }),
    }),
  );
  return buttons;
}

// Where each platform opens. The text is copied first, then the platform opens in a new tab.
// LinkedIn and X accept pre-filled text; Facebook and Instagram only open the page.
function publishTargets(post) {
  const encoded = encodeURIComponent(postText(post));
  return post.platforms.map((id) => {
    const channel = state.channels.find((c) => c.platform === id);
    let url = channel ? channel.url : '';
    let hint = 'Text copied.';
    if (id === 'linkedin') {
      url = `https://www.linkedin.com/feed/?shareActive=true&text=${encoded}`;
      hint = 'Text copied. LinkedIn opens with it filled in. To post as the company page, switch to it first.';
    } else if (id === 'twitter') {
      url = `https://x.com/intent/post?text=${encoded}`;
      hint = 'Text copied. X opens with it filled in.';
    } else if (id === 'facebook') {
      hint = url
        ? 'Text copied. On the page, choose Create post and paste.'
        : 'Add the Facebook page under Pages first.';
    } else if (id === 'instagram') {
      hint = url
        ? 'Text copied. Instagram posts are made in the Instagram app: add the photo and paste.'
        : 'Add the Instagram page under Pages first.';
    }
    return { id, label: `Post to ${platformLabel(id)}`, url, hint };
  });
}

function postNowBox(post) {
  if (post.status === 'posted' || post.platforms.length === 0) return null;
  const photos = post.media_ids.map(mediaById).filter(Boolean);
  const buttons = publishTargets(post).map((target) =>
    h('button', {
      class: 'btn small',
      text: target.label,
      title: target.hint,
      disabled: !target.url,
      onClick: async () => {
        await copyText(postText(post));
        toast(target.hint, target.url ? '' : 'error');
        if (target.url && !window.open(target.url, '_blank', 'noopener')) {
          toast('Your browser blocked the new tab. Allow pop-ups for this site.', 'error');
        }
      },
    }),
  );
  return h(
    'div',
    { class: 'postnow', style: 'flex:1 1 100%' },
    h('b', { text: 'Post now' }),
    h('div', { class: 'small muted', text: 'The text is copied for you, then the platform opens in a new tab.' }),
    h('div', { class: 'row' }, buttons),
    photos.length
      ? h(
          'div',
          { class: 'row small', style: 'margin-top:8px' },
          'Photos:',
          photos.map((m, i) => h('a', { href: mediaSrc(m), download: m.filename, text: `Download ${i + 1}` })),
        )
      : null,
  );
}

function statusBadge(post) {
  const due = isDue(post);
  const key = due ? 'due' : post.status;
  const label = { draft: 'Draft', scheduled: 'Scheduled', due: 'Due now', posted: 'Posted' }[key];
  return h('span', { class: `badge ${key}`, text: label });
}

function thumbsFor(ids) {
  const items = ids.map(mediaById).filter(Boolean);
  if (!items.length) return null;
  return h(
    'div',
    { class: 'thumbs' },
    items.map((m) => mediaTile(m)),
  );
}

function mediaTile(m, extra) {
  const visual = m.mime.startsWith('video/')
    ? h('video', { src: `${mediaSrc(m)}#t=0.1`, preload: 'metadata', muted: true, playsinline: true })
    : h('img', { src: mediaSrc(m), alt: m.caption || m.filename, loading: 'lazy' });
  return h('div', { class: 'thumb', title: m.caption || m.filename }, visual, extra);
}

function showPost(post) {
  const content = h(
    'div',
    { class: 'post-card' },
    h(
      'div',
      { class: 'meta' },
      statusBadge(post),
      post.platforms.map((id) => h('span', { class: 'row', style: 'gap:4px' }, icon(id), platformLabel(id))),
      post.scheduled_at ? h('span', { class: 'muted small', text: fmtDateTime(post.scheduled_at) }) : null,
    ),
    h('div', { class: 'body', text: postText(post) || '(no text)' }),
    thumbsFor(post.media_ids),
    h('div', { class: 'actions' }, postActions(post)),
  );
  openModal(`Post #${post.id}`, content);
}

// ---------------------------------------------------------------- compose view

function composeView() {
  const d = state.draft;
  const locked = d.status === 'posted';
  const root = h('div', { class: 'compose-grid' });
  let timer;
  let lastCheck = null;

  const title = h('h2', {});
  const setTitle = () => {
    title.textContent = d.id ? `Editing post #${d.id}` : 'New post';
  };
  setTitle();

  const platformPills = h(
    'div',
    { class: 'pills', role: 'group', 'aria-label': 'Platforms' },
    state.rules.platform_order.map((id) =>
      h(
        'label',
        { class: 'pill', for: `pf-${id}` },
        h('input', {
          type: 'checkbox',
          id: `pf-${id}`,
          checked: d.platforms.includes(id),
          onChange: (e) => {
            d.platforms = e.target.checked
              ? [...d.platforms, id]
              : d.platforms.filter((p) => p !== id);
            changedField();
          },
        }),
        h('span', { class: 'pill-body' }, icon(id), platformLabel(id)),
      ),
    ),
  );

  const counter = h('div', { class: 'counter' });
  const content = h('textarea', {
    id: 'content',
    placeholder: 'What would you like to share?',
    value: d.content,
    onInput: (e) => {
      d.content = e.target.value;
      changedField();
    },
  });
  const link = h('input', {
    type: 'text',
    id: 'link',
    placeholder: 'https://pukekoconstruction.co.nz/',
    value: d.link,
    onInput: (e) => {
      d.link = e.target.value;
      changedField();
    },
  });
  const hashtags = h('input', {
    type: 'text',
    id: 'hashtags',
    placeholder: '#recladding #auckland',
    value: d.hashtags,
    onInput: (e) => {
      d.hashtags = e.target.value;
      changedField();
    },
  });
  const when = h('input', {
    type: 'datetime-local',
    id: 'when',
    value: d.when,
    onInput: (e) => {
      d.when = e.target.value;
    },
  });

  const strip = h('div', { class: 'thumbs' });
  const renderStrip = () => {
    const tiles = d.media_ids
      .map(mediaById)
      .filter(Boolean)
      .map((m) =>
        mediaTile(
          m,
          locked
            ? null
            : h('button', {
                class: 'x',
                'aria-label': `Remove ${m.filename}`,
                text: '×',
                onClick: () => {
                  d.media_ids = d.media_ids.filter((id) => id !== m.id);
                  renderStrip();
                  changedField();
                },
              }),
        ),
      );
    strip.replaceChildren(...(tiles.length ? tiles : [h('span', { class: 'muted small', text: 'No photos or videos added.' })]));
  };

  const uploadInput = h('input', {
    type: 'file',
    accept: 'image/jpeg,image/png,image/gif,image/webp,image/heic,video/mp4,video/quicktime',
    multiple: true,
    style: 'display:none',
    onChange: async (e) => {
      const files = [...e.target.files];
      e.target.value = '';
      for (const file of files) {
        try {
          const media = await uploadFile(file, '', '');
          d.media_ids = [...d.media_ids, media.id];
        } catch (err) {
          toast(explain(err), 'error');
        }
      }
      await refreshMedia();
      renderStrip();
      changedField();
    },
  });

  const checkBox = h('div', { 'aria-live': 'polite' });
  const previews = h('div', { class: 'stack' });

  function localLength(id) {
    const rule = state.rules.platforms[id];
    const c = d.content.trim();
    const l = d.link.trim();
    const t = d.hashtags.trim();
    let total = Array.from(c).length;
    if (l) total += (total ? 1 : 0) + (rule.linkLength ?? Array.from(l).length);
    if (t) total += (total ? 1 : 0) + Array.from(t).length;
    return total;
  }

  function renderPreviews() {
    const cards = d.platforms.map((id) => {
      const rule = state.rules.platforms[id];
      const length = localLength(id);
      const over = length > rule.limit;
      return h(
        'div',
        { class: 'preview' },
        h('h4', {}, icon(id), platformLabel(id)),
        h('div', { class: 'body', text: d.content || 'Your text appears here.' }),
        d.link.trim() ? h('div', { class: 'linkline', text: d.link.trim() }) : null,
        d.hashtags.trim() ? h('div', { class: 'linkline', text: d.hashtags.trim() }) : null,
        thumbsFor(d.media_ids),
        h('div', { class: `foot${over ? ' over' : ''}`, text: `${length} / ${rule.limit} characters` }),
      );
    });
    previews.replaceChildren(
      ...(cards.length ? cards : [h('p', { class: 'muted', text: 'Pick a platform to see how the post will look.' })]),
    );
  }

  function renderCheck(check, extraProblems = []) {
    const items = [];
    for (const message of extraProblems) {
      items.push(h('div', { class: 'notice err' }, h('b', { text: 'Fix: ' }), message));
    }
    if (check) {
      for (const err of check.errors) {
        items.push(h('div', { class: 'notice err' }, h('b', { text: 'Blocked: ' }), err.message));
      }
      for (const warn of check.warnings) {
        items.push(h('div', { class: 'notice warn' }, h('b', { text: 'Check: ' }), warn.message));
      }
      if (check.ok && check.warnings.length === 0 && d.content.trim() && d.platforms.length) {
        items.push(h('div', { class: 'notice ok', text: 'Passes all Pukeko checks.' }));
      }
    }
    checkBox.replaceChildren(...items);
  }

  async function runCheck() {
    try {
      const res = await api('POST', '/api/check', {
        content: d.content,
        link: d.link,
        hashtags: d.hashtags,
        platforms: d.platforms,
        media_ids: d.media_ids,
      });
      lastCheck = res.check;
      renderCheck(lastCheck);
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) renderCheck(null, [explain(err)]);
    }
  }

  function changedField() {
    counter.textContent = `${Array.from(d.content).length} characters`;
    renderPreviews();
    clearTimeout(timer);
    timer = setTimeout(runCheck, 250);
  }

  const payload = () => ({
    content: d.content,
    link: d.link,
    hashtags: d.hashtags,
    platforms: d.platforms,
    media_ids: d.media_ids,
  });

  async function save() {
    const res = d.id ? await api('PUT', `/api/posts/${d.id}`, payload()) : await api('POST', '/api/posts', payload());
    d.id = res.post.id;
    d.status = res.post.status;
    setTitle();
    await refreshPosts();
    return res;
  }

  const onSave = async () => {
    try {
      await save();
      toast(d.status === 'scheduled' ? 'Changes saved.' : 'Draft saved.');
    } catch (err) {
      renderCheck(err.data && err.data.check ? err.data.check : lastCheck, err.data && err.data.problems ? err.data.problems : []);
      toast(explain(err), 'error');
    }
  };

  const onSchedule = async () => {
    if (!d.when) {
      toast('Choose a date and time first.', 'error');
      when.focus();
      return;
    }
    try {
      await save();
      const iso = new Date(d.when).toISOString();
      await api('POST', `/api/posts/${d.id}/schedule`, { scheduled_at: iso });
      await refreshPosts();
      toast('Scheduled.');
      state.calMonth = startOfMonth(new Date(d.when));
      state.draft = blankDraft();
      go('calendar');
    } catch (err) {
      renderCheck(err.data && err.data.check ? err.data.check : lastCheck, err.data && err.data.problems ? err.data.problems : []);
      toast(explain(err), 'error');
    }
  };

  const onUnschedule = async () => {
    try {
      await api('POST', `/api/posts/${d.id}/unschedule`);
      d.status = 'draft';
      await refreshPosts();
      toast('Moved back to drafts.');
      renderApp();
    } catch (err) {
      toast(explain(err), 'error');
    }
  };

  const onNew = () => {
    state.draft = blankDraft();
    renderApp();
  };

  const library = () =>
    openLibrary(d.media_ids, (ids) => {
      d.media_ids = ids;
      renderStrip();
      changedField();
    });

  const actions = locked
    ? h('div', { class: 'notice warn', text: 'This post is already marked as posted. Use Duplicate on the Posts page to reuse it.' })
    : h(
        'div',
        { class: 'row' },
        h('button', { class: 'btn', text: 'Save draft', onClick: onSave }),
        h('button', { class: 'btn primary', text: d.status === 'scheduled' ? 'Update schedule' : 'Schedule', onClick: onSchedule }),
        d.status === 'scheduled' ? h('button', { class: 'btn', text: 'Unschedule', onClick: onUnschedule }) : null,
        h('button', { class: 'btn ghost', text: 'New post', onClick: onNew }),
      );

  if (locked) {
    for (const el of [content, link, hashtags, when]) el.disabled = true;
  }

  root.append(
    h(
      'section',
      { class: 'card stack' },
      h('div', { class: 'row spread' }, title, d.id ? statusBadge({ status: d.status, scheduled_at: d.when ? new Date(d.when).toISOString() : null }) : null),
      h('div', {}, h('div', { class: 'field', text: 'Platforms' }), platformPills),
      h('div', {}, h('label', { class: 'field', for: 'content', text: 'Post text' }), content, counter),
      h('div', {}, h('label', { class: 'field', for: 'link', text: 'Link (optional)' }), link),
      h('div', {}, h('label', { class: 'field', for: 'hashtags', text: 'Hashtags (optional)' }), hashtags),
      h(
        'div',
        {},
        h('div', { class: 'field', text: 'Photos and videos' }),
        strip,
        locked
          ? null
          : h(
              'div',
              { class: 'row', style: 'margin-top:10px' },
              h('button', { class: 'btn small', text: 'Choose from library', onClick: library }),
              h('button', { class: 'btn small', text: 'Upload new', onClick: () => uploadInput.click() }),
              uploadInput,
            ),
      ),
      h('div', {}, h('label', { class: 'field', for: 'when', text: 'Publish date and time' }), when),
      actions,
    ),
    h(
      'section',
      { class: 'stack' },
      h('div', { class: 'card' }, h('h3', { text: 'Checks', style: 'margin-bottom:10px' }), checkBox),
      h('div', { class: 'card stack' }, h('h3', { text: 'Preview' }), previews),
    ),
  );

  renderStrip();
  changedField();
  return root;
}

// ---------------------------------------------------------------- media helpers

const EXT_TYPES = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  gif: 'image/gif',
  webp: 'image/webp',
  heic: 'image/heic',
  mp4: 'video/mp4',
  mov: 'video/quicktime',
};

async function uploadFile(file, project, caption) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  const type = file.type || EXT_TYPES[ext] || 'application/octet-stream';
  const query = new URLSearchParams({ filename: file.name, project, caption });
  const res = await api('POST', `/api/media?${query}`, undefined, { blob: file, type });
  return res.media;
}

function openLibrary(selectedIds, onDone) {
  const chosen = new Set(selectedIds);
  const grid = h('div', { class: 'photo-grid' });
  const draw = () => {
    grid.replaceChildren(
      ...state.media.map((m) =>
        h(
          'div',
          {
            class: `photo pick${chosen.has(m.id) ? ' on' : ''}`,
            role: 'checkbox',
            tabindex: '0',
            'aria-checked': chosen.has(m.id) ? 'true' : 'false',
            onClick: () => {
              if (chosen.has(m.id)) chosen.delete(m.id);
              else chosen.add(m.id);
              draw();
            },
            onKeydown: (e) => {
              if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                e.currentTarget.click();
              }
            },
          },
          h('div', { class: 'shot' }, mediaTile(m).firstChild),
          h('div', { class: 'info small' }, h('b', { text: m.project || 'No project' }), h('span', { class: 'muted', text: m.caption || m.filename })),
        ),
      ),
    );
    if (!state.media.length) grid.replaceChildren(h('p', { class: 'empty', text: 'No photos yet. Upload some from the Photos page.' }));
  };
  draw();
  openModal(
    'Choose from the photo library',
    h(
      'div',
      { class: 'stack' },
      grid,
      h(
        'div',
        { class: 'row' },
        h('button', {
          class: 'btn primary',
          text: 'Use selected',
          onClick: () => {
            onDone([...chosen]);
            closeModal();
          },
        }),
      ),
    ),
    { wide: true },
  );
}

// ---------------------------------------------------------------- calendar view

function dueSection() {
  const due = state.posts.filter(isDue);
  if (!due.length) return null;
  return h(
    'section',
    { class: 'card stack', style: 'border-color:var(--warn)' },
    h('h3', { text: `Due now (${due.length})` }),
    h('p', { class: 'muted small', text: 'These were scheduled for a time that has passed. Post them, then mark them as posted.' }),
    due.map((post) =>
      h(
        'div',
        { class: 'post-card' },
        h('div', { class: 'meta' }, statusBadge(post), h('span', { class: 'muted small', text: fmtDateTime(post.scheduled_at) })),
        h('div', { class: 'body', text: excerpt(post.content, 220) }),
        h('div', { class: 'actions' }, postActions(post)),
      ),
    ),
  );
}

function calendarView() {
  const month = state.calMonth;
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - offset);
  const todayKey = dayKey(new Date());

  const byDay = new Map();
  for (const post of state.posts) {
    const iso = post.status === 'posted' ? post.posted_at : post.scheduled_at;
    if (!iso) continue;
    const key = dayKey(new Date(iso));
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push({ post, iso });
  }
  for (const list of byDay.values()) list.sort((a, b) => Date.parse(a.iso) - Date.parse(b.iso));

  const cells = [];
  for (const name of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
    cells.push(h('div', { class: 'dow', text: name }));
  }
  for (let i = 0; i < 42; i += 1) {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    const key = dayKey(date);
    const entries = byDay.get(key) || [];
    const classes = ['day'];
    if (date.getMonth() !== month.getMonth()) classes.push('other');
    if (key === todayKey) classes.push('today');
    cells.push(
      h(
        'div',
        {
          class: classes.join(' '),
          onClick: () => {
            const at = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 9, 0);
            state.draft = blankDraft();
            if (at.getTime() > Date.now()) state.draft.when = toLocalInput(at.toISOString());
            go('compose');
          },
        },
        h('div', { class: 'num', text: String(date.getDate()) }),
        entries.map(({ post, iso }) =>
          h('button', {
            class: `chip ${isDue(post) ? 'due' : post.status}`,
            title: excerpt(post.content, 120),
            text: `${fmtTime(iso)} ${excerpt(post.content, 24)}`,
            onClick: (e) => {
              e.stopPropagation();
              showPost(post);
            },
          }),
        ),
      ),
    );
  }

  const shift = (delta) => {
    state.calMonth = new Date(month.getFullYear(), month.getMonth() + delta, 1);
    renderApp();
  };

  const drafts = state.posts.filter((p) => p.status === 'draft');

  return h(
    'div',
    { class: 'stack' },
    dueSection(),
    h(
      'section',
      { class: 'card' },
      h(
        'div',
        { class: 'cal-head' },
        h('button', { class: 'btn small', 'aria-label': 'Previous month', text: '‹', onClick: () => shift(-1) }),
        h('h2', { text: month.toLocaleDateString('en-NZ', { month: 'long', year: 'numeric' }) }),
        h('div', { class: 'row' },
          h('button', {
            class: 'btn small',
            text: 'Today',
            onClick: () => {
              state.calMonth = startOfMonth(new Date());
              renderApp();
            },
          }),
          h('button', { class: 'btn small', 'aria-label': 'Next month', text: '›', onClick: () => shift(1) }),
        ),
      ),
      h('div', { class: 'cal' }, cells),
      h('p', { class: 'muted small', text: 'Click a day to start a post for it. Click a post to open it.' }),
    ),
    drafts.length
      ? h(
          'section',
          { class: 'card stack' },
          h('h3', { text: `Unscheduled drafts (${drafts.length})` }),
          drafts.map((post) =>
            h(
              'div',
              { class: 'row spread' },
              h('span', { class: 'grow', text: excerpt(post.content, 90) }),
              h('button', { class: 'btn small', text: 'Open', onClick: () => editPost(post) }),
            ),
          ),
        )
      : null,
  );
}

// ---------------------------------------------------------------- posts view

function postsView() {
  const filters = [
    ['all', 'All'],
    ['draft', 'Drafts'],
    ['scheduled', 'Scheduled'],
    ['due', 'Due now'],
    ['posted', 'Posted'],
  ];
  const matches = (post) => {
    if (state.filter === 'all') return true;
    if (state.filter === 'due') return isDue(post);
    return post.status === state.filter;
  };
  const posts = state.posts.filter(matches);

  const tabs = h(
    'div',
    { class: 'tabs' },
    filters.map(([id, label]) =>
      h('button', {
        'aria-pressed': state.filter === id ? 'true' : 'false',
        text: label,
        onClick: () => {
          state.filter = id;
          renderApp();
        },
      }),
    ),
  );

  const cards = posts.map((post) =>
    h(
      'article',
      { class: 'card post-card' },
      h(
        'div',
        { class: 'meta' },
        statusBadge(post),
        post.platforms.map((id) => h('span', { class: 'row', style: 'gap:4px' }, icon(id), platformLabel(id))),
        post.scheduled_at && post.status !== 'posted' ? h('span', { class: 'muted small', text: fmtDateTime(post.scheduled_at) }) : null,
        post.posted_at && post.status === 'posted' ? h('span', { class: 'muted small', text: `Posted ${fmtDateTime(post.posted_at)}` }) : null,
      ),
      h('div', { class: 'body', text: postText(post) || '(no text)' }),
      thumbsFor(post.media_ids),
      h('div', { class: 'actions' }, postActions(post)),
    ),
  );

  return h(
    'div',
    { class: 'stack' },
    h('div', { class: 'row spread' }, h('h2', { text: 'Posts' }), h('button', { class: 'btn primary', text: 'New post', onClick: () => { state.draft = blankDraft(); go('compose'); } })),
    tabs,
    cards.length ? h('div', { class: 'list' }, cards) : h('div', { class: 'card empty', text: 'Nothing here yet.' }),
  );
}

// ---------------------------------------------------------------- photos view

function photosView() {
  const projects = [...new Set(state.media.map((m) => m.project).filter(Boolean))].sort();
  const shown = state.media.filter((m) => !state.projectFilter || m.project === state.projectFilter);

  const projectInput = h('input', { type: 'text', id: 'up-project', placeholder: 'Project, e.g. Ponsonby recladding', list: 'projects' });
  const captionInput = h('input', { type: 'text', id: 'up-caption', placeholder: 'Caption, e.g. Before' });
  const fileInput = h('input', {
    type: 'file',
    accept: 'image/jpeg,image/png,image/gif,image/webp,image/heic,video/mp4,video/quicktime',
    multiple: true,
    style: 'display:none',
    onChange: async (e) => {
      const files = [...e.target.files];
      e.target.value = '';
      let ok = 0;
      for (const file of files) {
        try {
          await uploadFile(file, projectInput.value.trim(), captionInput.value.trim());
          ok += 1;
        } catch (err) {
          toast(`${file.name}: ${explain(err)}`, 'error');
        }
      }
      if (ok) toast(`${ok} uploaded.`);
      await refreshMedia();
      renderApp();
    },
  });

  const cards = shown.map((m) => {
    const project = h('input', { type: 'text', value: m.project, placeholder: 'Project', 'aria-label': 'Project' });
    const caption = h('input', { type: 'text', value: m.caption, placeholder: 'Caption', 'aria-label': 'Caption' });
    const save = async () => {
      if (project.value === m.project && caption.value === m.caption) return;
      try {
        const res = await api('PATCH', `/api/media/${m.id}`, { project: project.value.trim(), caption: caption.value.trim() });
        Object.assign(m, res.media);
        toast('Saved.');
      } catch (err) {
        toast(explain(err), 'error');
      }
    };
    project.addEventListener('change', save);
    caption.addEventListener('change', save);
    return h(
      'div',
      { class: 'photo' },
      h('div', { class: 'shot' }, mediaTile(m).firstChild),
      h(
        'div',
        { class: 'info' },
        project,
        caption,
        h('button', {
          class: 'btn small danger',
          text: 'Delete',
          onClick: async () => {
            if (!window.confirm('Delete this photo?')) return;
            try {
              await api('DELETE', `/api/media/${m.id}`);
              await refreshMedia();
              renderApp();
            } catch (err) {
              toast(explain(err), 'error');
            }
          },
        }),
      ),
    );
  });

  return h(
    'div',
    { class: 'stack' },
    h('h2', { text: 'Photo library' }),
    h(
      'section',
      { class: 'card stack' },
      h('p', { class: 'muted small', text: 'Upload job photos once, then reuse them in any post. JPEG, PNG, GIF, WebP, HEIC, MP4 and MOV, up to 50 MB each.' }),
      h('div', { class: 'row' }, h('div', { class: 'grow' }, projectInput), h('div', { class: 'grow' }, captionInput)),
      h('datalist', { id: 'projects' }, projects.map((p) => h('option', { value: p }))),
      h('div', {}, h('button', { class: 'btn primary', text: 'Upload photos or videos', onClick: () => fileInput.click() }), fileInput),
    ),
    projects.length
      ? h(
          'div',
          { class: 'tabs' },
          [['', 'All projects'], ...projects.map((p) => [p, p])].map(([value, label]) =>
            h('button', {
              'aria-pressed': state.projectFilter === value ? 'true' : 'false',
              text: label,
              onClick: () => {
                state.projectFilter = value;
                renderApp();
              },
            }),
          ),
        )
      : null,
    cards.length ? h('div', { class: 'photo-grid' }, cards) : h('div', { class: 'card empty', text: 'No photos yet.' }),
  );
}

// ---------------------------------------------------------------- pages view

const CHANNEL_LABELS = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  linkedin: 'LinkedIn',
  twitter: 'X',
  youtube: 'YouTube',
  tiktok: 'TikTok',
  google: 'Google Business Profile',
  website: 'Website',
  other: 'Other',
};

function channelIcon(platform) {
  if (ICONS[platform]) return icon(platform);
  const span = document.createElement('span');
  span.className = 'pf-generic';
  span.textContent = (CHANNEL_LABELS[platform] || platform).charAt(0).toUpperCase();
  return span;
}

function pagesView() {
  let editingId = null;
  const platform = h(
    'select',
    { id: 'ch-platform', 'aria-label': 'Platform' },
    state.channelPlatforms.map((id) => h('option', { value: id, text: CHANNEL_LABELS[id] || id })),
  );
  const name = h('input', { type: 'text', id: 'ch-name', placeholder: 'Page name, e.g. Pukeko Construction', 'aria-label': 'Page name' });
  const url = h('input', { type: 'text', id: 'ch-url', placeholder: 'https://www.linkedin.com/company/…', 'aria-label': 'Page address' });
  const notes = h('input', { type: 'text', id: 'ch-notes', placeholder: 'Notes (optional)', 'aria-label': 'Notes' });
  const submit = h('button', { class: 'btn primary', text: 'Add page' });
  const cancel = h('button', { class: 'btn ghost', text: 'Cancel', style: 'display:none' });
  const formTitle = h('h3', { text: 'Add a page' });

  const reset = () => {
    editingId = null;
    name.value = '';
    url.value = '';
    notes.value = '';
    platform.value = state.channelPlatforms[0];
    submit.textContent = 'Add page';
    formTitle.textContent = 'Add a page';
    cancel.style.display = 'none';
  };

  const startEdit = (channel) => {
    editingId = channel.id;
    platform.value = channel.platform;
    name.value = channel.name;
    url.value = channel.url;
    notes.value = channel.notes;
    submit.textContent = 'Save changes';
    formTitle.textContent = `Edit ${channel.name}`;
    cancel.style.display = '';
    name.focus();
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  };

  submit.addEventListener('click', async () => {
    const body = { platform: platform.value, name: name.value, url: url.value, notes: notes.value };
    try {
      if (editingId) await api('PUT', `/api/channels/${editingId}`, body);
      else await api('POST', '/api/channels', body);
      await refreshChannels();
      toast(editingId ? 'Page updated.' : 'Page added.');
      renderApp();
    } catch (err) {
      toast(explain(err), 'error');
    }
  });
  cancel.addEventListener('click', reset);

  const cards = state.channels.map((channel) =>
    h(
      'article',
      { class: 'card channel' },
      h(
        'div',
        { class: 'who' },
        channelIcon(channel.platform),
        h(
          'div',
          { class: 'text' },
          h('div', {}, h('b', { text: channel.name }), ' ', h('span', { class: 'muted small', text: CHANNEL_LABELS[channel.platform] || channel.platform })),
          h('div', { class: 'url', text: channel.url }),
          channel.notes ? h('div', { class: 'muted small', text: channel.notes }) : null,
        ),
      ),
      h(
        'div',
        { class: 'actions' },
        h('a', { class: 'btn small primary', href: channel.url, target: '_blank', rel: 'noopener noreferrer', text: 'Open' }),
        h('button', { class: 'btn small', text: 'Copy link', onClick: () => copyText(channel.url) }),
        h('button', { class: 'btn small', text: 'Edit', onClick: () => startEdit(channel) }),
        h('button', {
          class: 'btn small danger',
          text: 'Remove',
          onClick: async () => {
            if (!window.confirm(`Remove ${channel.name} from the list? This does not touch the real page.`)) return;
            try {
              await api('DELETE', `/api/channels/${channel.id}`);
              await refreshChannels();
              renderApp();
            } catch (err) {
              toast(explain(err), 'error');
            }
          },
        }),
      ),
    ),
  );

  const hasLinkedIn = state.channels.some((c) => c.platform === 'linkedin');
  reset();

  return h(
    'div',
    { class: 'stack' },
    h('h2', { text: 'Pukeko pages and accounts' }),
    h('p', { class: 'muted', text: 'Every page Pukeko posts to, in one list. Open any of them, or use Post now on a post to copy the text and jump straight to the right page.' }),
    hasLinkedIn
      ? null
      : h('div', { class: 'notice warn' }, h('b', { text: 'No LinkedIn page yet. ' }), 'The Pukeko website does not link to one. Add its address below.'),
    cards.length ? h('div', { class: 'list' }, cards) : h('div', { class: 'card empty', text: 'No pages yet.' }),
    h(
      'section',
      { class: 'card stack' },
      formTitle,
      h('div', { class: 'form-grid' }, platform, name, url),
      notes,
      h('div', { class: 'row' }, submit, cancel),
    ),
  );
}

// ---------------------------------------------------------------- boot

async function boot() {
  try {
    state.rules = await api('GET', '/api/rules');
    await Promise.all([refreshPosts(), refreshMedia(), refreshChannels()]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return;
    document.getElementById('app').replaceChildren(
      h('main', {}, h('div', { class: 'card notice err', text: `Could not reach the SocialSync server. ${explain(err)}` })),
    );
    return;
  }
  renderApp();
}

// Keep the "Due now" markers fresh without disturbing a post being written.
setInterval(async () => {
  if (!state.rules || activeModal || state.view === 'compose') return;
  try {
    await refreshPosts();
    renderApp();
  } catch {
    // ignore: the next tick will retry
  }
}, 60_000);

boot();
