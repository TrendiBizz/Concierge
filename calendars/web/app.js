// Concierge Calendars dashboard. Vanilla ES module, no dependencies. All
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

const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

const state = {
  tenant: null,
  view: 'book',
  windows: [],
  appointments: [],
  slotDate: todayStr(),
  slots: [],
  selectedSlot: null,
};

function todayStr() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fmtTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
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
        h('p', { class: 'muted', text: 'Calendars: bookings' }),
        h('div', {}, h('label', { class: 'field', text: 'Passcode' }), input, message),
        h('button', { class: 'btn primary', onClick: submit, text: 'Sign in' }),
      ),
    ),
  );
  input.focus();
}

// ---------------------------------------------------------------- availability view

function availabilityView() {
  const weekday = h('select', {}, WEEKDAYS.map((name, i) => h('option', { value: i, text: name })));
  const start = h('input', { type: 'time', value: '09:00' });
  const end = h('input', { type: 'time', value: '17:00' });
  const slotMinutes = h('input', { type: 'number', value: '30', min: '5', max: '480', step: '5' });

  const add = async () => {
    try {
      await api('POST', '/api/windows', {
        weekday: Number(weekday.value),
        start: start.value,
        end: end.value,
        slot_minutes: Number(slotMinutes.value) || 30,
      });
      await refreshWindows();
      toast('Availability window added.');
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  return h(
    'div',
    {},
    h('h2', { text: 'Availability' }),
    h(
      'table',
      {},
      h('thead', {}, h('tr', {}, h('th', { text: 'Day' }), h('th', { text: 'Start' }), h('th', { text: 'End' }), h('th', { text: 'Slot length' }), h('th', {}))),
      h(
        'tbody',
        {},
        state.windows.map((w) =>
          h(
            'tr',
            {},
            h('td', { text: WEEKDAYS[w.weekday] }),
            h('td', { text: minutesToHHMM(w.start_minutes) }),
            h('td', { text: minutesToHHMM(w.end_minutes) }),
            h('td', { text: `${w.slot_minutes} min` }),
            h(
              'td',
              {},
              h('button', {
                class: 'btn small',
                text: 'Remove',
                onClick: async () => {
                  await api('DELETE', `/api/windows/${w.id}`);
                  await refreshWindows();
                  renderApp();
                },
              }),
            ),
          ),
        ),
      ),
    ),
    h('h3', { style: 'margin-top:20px', text: 'Add a window' }),
    h(
      'div',
      { class: 'card row', style: 'max-width:600px' },
      weekday,
      h('label', { class: 'field', text: 'Start' }),
      start,
      h('label', { class: 'field', text: 'End' }),
      end,
      h('label', { class: 'field', text: 'Slot (min)' }),
      slotMinutes,
      h('button', { class: 'btn primary', onClick: add, text: 'Add window' }),
    ),
  );
}

function minutesToHHMM(m) {
  const hh = String(Math.floor(m / 60)).padStart(2, '0');
  const mm = String(m % 60).padStart(2, '0');
  return `${hh}:${mm}`;
}

// ---------------------------------------------------------------- book view

function bookView() {
  const dateInput = h('input', {
    type: 'date',
    value: state.slotDate,
    onChange: async (e) => {
      state.slotDate = e.target.value;
      state.selectedSlot = null;
      await refreshSlots();
      renderApp();
    },
  });

  const slotButtons = state.slots.map((s) =>
    h('button', {
      class: `btn slot-btn${state.selectedSlot === s.start_at ? ' selected' : ''}`,
      text: new Date(s.start_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }),
      onClick: () => {
        state.selectedSlot = s.start_at;
        renderApp();
      },
    }),
  );

  const name = h('input', { placeholder: 'Contact name' });
  const email = h('input', { placeholder: 'Email (optional)' });
  const phone = h('input', { placeholder: 'Phone (optional)' });
  const notes = h('input', { placeholder: 'Notes (optional)' });

  const book = async () => {
    if (!state.selectedSlot) return toast('Pick a time first.', 'error');
    if (!name.value.trim()) return toast('Contact name is required.', 'error');
    const slot = state.slots.find((s) => s.start_at === state.selectedSlot);
    try {
      await api('POST', '/api/appointments', {
        contact_name: name.value.trim(),
        contact_email: email.value.trim(),
        contact_phone: phone.value.trim(),
        notes: notes.value.trim(),
        start_at: slot.start_at,
        duration_minutes: slot.duration_minutes,
      });
      toast('Booked.');
      state.selectedSlot = null;
      name.value = '';
      email.value = '';
      phone.value = '';
      notes.value = '';
      await Promise.all([refreshSlots(), refreshAppointments()]);
      renderApp();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  return h(
    'div',
    {},
    h('h2', { text: 'Book an appointment' }),
    h('div', { class: 'row', style: 'margin-bottom:10px' }, h('label', { class: 'field', text: 'Date' }), dateInput),
    state.slots.length === 0
      ? h('p', { class: 'muted', text: 'No open slots on this date.' })
      : h('div', { class: 'slot-grid', style: 'margin-bottom:16px' }, slotButtons),
    state.selectedSlot
      ? h(
          'div',
          { class: 'card stack', style: 'max-width:380px' },
          h('p', { class: 'small muted', text: `Booking ${fmtTime(state.selectedSlot)}` }),
          name,
          email,
          phone,
          notes,
          h('button', { class: 'btn primary', onClick: book, text: 'Book it' }),
        )
      : null,
  );
}

// ---------------------------------------------------------------- appointments view

function appointmentsView() {
  const upcoming = [...state.appointments].sort((a, b) => Date.parse(a.start_at) - Date.parse(b.start_at));
  return h(
    'div',
    {},
    h('h2', { text: 'Appointments' }),
    upcoming.length === 0
      ? h('p', { class: 'muted', text: 'No appointments yet.' })
      : upcoming.map((a) =>
          h(
            'div',
            { class: 'appt' },
            h(
              'div',
              {},
              h('div', { class: 'when', text: fmtTime(a.start_at) }),
              h('div', { class: 'small muted', text: `${a.contact_name}${a.contact_email ? ` · ${a.contact_email}` : ''}` }),
            ),
            h('span', { class: `badge ${a.status}`, text: a.status }),
            h(
              'div',
              { class: 'row' },
              a.status === 'booked'
                ? h('button', {
                    class: 'btn small',
                    text: 'Mark completed',
                    onClick: async () => {
                      await api('POST', `/api/appointments/${a.id}/status`, { status: 'completed' });
                      await refreshAppointments();
                      renderApp();
                    },
                  })
                : null,
              a.status === 'booked'
                ? h('button', {
                    class: 'btn small',
                    text: 'Cancel',
                    onClick: async () => {
                      await api('POST', `/api/appointments/${a.id}/status`, { status: 'cancelled' });
                      await refreshAppointments();
                      await refreshSlots();
                      renderApp();
                    },
                  })
                : null,
              h('button', {
                class: 'btn small',
                text: 'Delete',
                onClick: async () => {
                  await api('DELETE', `/api/appointments/${a.id}`);
                  await refreshAppointments();
                  await refreshSlots();
                  renderApp();
                },
              }),
            ),
          ),
        ),
  );
}

// ---------------------------------------------------------------- shell

async function refreshWindows() {
  state.windows = (await api('GET', '/api/windows')).windows;
}
async function refreshSlots() {
  state.slots = (await api('GET', `/api/slots?date=${state.slotDate}`)).slots;
}
async function refreshAppointments() {
  state.appointments = (await api('GET', '/api/appointments')).appointments;
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
      h('nav', { class: 'tabs' }, tab('book', 'Book'), tab('appointments', 'Appointments'), tab('availability', 'Availability')),
      state.view === 'book' ? bookView() : state.view === 'appointments' ? appointmentsView() : availabilityView(),
    ),
  );
}

async function boot() {
  try {
    await Promise.all([refreshWindows(), refreshSlots(), refreshAppointments()]);
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
