import {lazy, Suspense, useEffect, useMemo, useState} from 'react';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import {Theme, defineTheme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {FileInput} from '@astryxdesign/core/FileInput';
import {Banner} from '@astryxdesign/core/Banner';
import {TabList, Tab} from '@astryxdesign/core/TabList';
import {NotifyProvider, useNotify} from './Notify';
import {AppShell} from '@astryxdesign/core/AppShell';
import {SideNav, SideNavSection, SideNavItem} from '@astryxdesign/core/SideNav';
import {InternationalizationProvider} from '@astryxdesign/core/i18n';
import en from './locales/en.json';
const navLoaders = import.meta.glob<{default: Record<string, string>}>('./i18n/nav/*.json');
const copyLoaders = import.meta.glob<{default: Record<string, string>}>('./i18n/copy/*.json');

const localeLoaders = import.meta.glob<{default: Record<string, string>}>('./locales/*.json');


const Home = lazy(() => import('./Home'));
const Designs = lazy(() => import('./Designs'));
const ProductsPage = lazy(() => import('./Products'));
const PermissionsPage = lazy(() => import('./Permissions'));
const Crm = lazy(() => import('./CrmQuotes').then((m) => ({default: m.Crm})));
const Quotes = lazy(() => import('./CrmQuotes').then((m) => ({default: m.Quotes})));
const Contacts = lazy(() => import('./CrmQuotes').then((m) => ({default: m.Contacts})));
const Media = lazy(() => import('./Engage').then((m) => ({default: m.Media})));
const Social = lazy(() => import('./Engage').then((m) => ({default: m.Social})));

type Brand = {name: string; accent: string; contact: string; logo?: string | null};
const CATALOGS: Record<string, Record<string, string>> = {en};
const LOCALES: Array<[string, string]> = [
  ['en', 'English'], ['af-ZA', 'Afrikaans'], ['ar-SA', 'العربية'], ['ca-ES', 'Català'],
  ['cs-CZ', 'Čeština'], ['da-DK', 'Dansk'], ['de-DE', 'Deutsch'], ['el-GR', 'Ελληνικά'],
  ['es-ES', 'Español'], ['fi-FI', 'Suomi'], ['fr-FR', 'Français'], ['he-IL', 'עברית'],
  ['hu-HU', 'Magyar'], ['it-IT', 'Italiano'], ['ja-JP', '日本語'], ['ko-KR', '한국어'],
  ['nl-NL', 'Nederlands'], ['no-NO', 'Norsk'], ['pl-PL', 'Polski'], ['pt-BR', 'Português (BR)'],
  ['pt-PT', 'Português (PT)'], ['ro-RO', 'Română'], ['ru-RU', 'Русский'], ['sr-SP', 'Српски'],
  ['sv-SE', 'Svenska'], ['tr-TR', 'Türkçe'], ['uk-UA', 'Українська'], ['vi-VN', 'Tiếng Việt'],
  ['zh-CN', '中文（简体）'], ['zh-TW', '中文（繁體）'],
];
// Only locales a human has actually reviewed are exposed to customers.
const REVIEWED = new Set(['en', 'af-ZA']);
const LOCALE_PREFIX = (value: string) => LOCALES.find(([code]) => code.toLowerCase().startsWith(value.toLowerCase().split('-')[0]))?.[0] || 'en';
const hasLocale = (code: string) => LOCALES.some(([item]) => item === code);

function initialLocale() {
  const query = new URLSearchParams(location.search).get('lang');
  if (query && hasLocale(LOCALE_PREFIX(query))) return LOCALE_PREFIX(query);
  const saved = localStorage.getItem('concierge.locale');
  if (saved && hasLocale(saved)) return saved;
  if (navigator.language) return LOCALE_PREFIX(navigator.language);
  return 'en';
}
type Asset = {id: string; kind: string; template: string; prompt: string; format: string; created_at: string};
type Business = {name: string; site_url: string; notify_email: string; notify_phone: string; public_key: string};
type Post = {id: string; status: string; content: string; link?: string; hashtags?: string; last_error?: string; scheduled_at?: number | string; created_at?: string};
type Lead = {id: string; name?: string; email?: string; phone?: string; channel: string; status: string; created_at: string; message?: string};
type QuoteLine = {description: string; quantity: number; unit_price_cents: number; amount_cents?: number};
type Quote = {id: string; title: string; currency: string; status: string; lines: QuoteLine[]; subtotal_cents: number; tax_cents: number; total_cents: number; notes?: string; created_at: string; lead_id: string; version: number; public_token?: string; sent_at?: string};

function readRaw(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Could not read ' + file.name));
    reader.readAsDataURL(file);
  });
}


function useApi(token: string) {
  return async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {'Accept': 'application/json', ...(body !== undefined ? {'Content-Type': 'application/json'} : {}), ...(token ? {Authorization: 'Bearer ' + token} : {})},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Request failed (' + response.status + ')');
    return data;
  };
}


function TranslationNote({locale}: {locale: string}) {
  if (REVIEWED.has(locale)) return null;
  const label = LOCALES.find(([code]) => code === locale)?.[1] || locale;
  return (
    <Banner
      status="warning"
      title={label + ' translation'}
      description={<>Automated and not reviewed by a native speaker. We welcome corrections — <a href={'mailto:admin@trendibizz.com?subject=' + encodeURIComponent('Translation feedback: ' + locale)}>tell us what to improve</a>.</>}
      isDismissable
    />
  );
}

function BrandHeader({brand, tab, setTab, onSignOut, onInstall, locale, setLocale, tr, mode, setMode, showTabs = true, layout, setLayout}: {brand: Brand; tab: string; setTab: (v: string) => void; onSignOut: () => void; onInstall?: () => void; locale: string; setLocale: (v: string) => void; tr: (key: string) => string; mode: string; setMode: (v: string) => void; showTabs?: boolean; layout: string; setLayout: (v: string) => void}) {
  return (
    <header style={{borderBottom: '1px solid var(--color-border)', padding: '16px 0', marginBottom: 24}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', maxWidth: 1040, margin: '0 auto', padding: '0 24px'}}>
        {brand.logo ? <img src={brand.logo} alt="" style={{height: 44, width: 'auto'}} /> : null}
        <div style={{display: 'flex', flexDirection: 'column'}}>
          <strong style={{fontSize: 20}}>{brand.name || 'Concierge'}</strong>
          <span style={{fontSize: 13, color: 'var(--color-text-secondary)'}}>Powered by Trendi</span>
        </div>
        <div style={{display: 'flex', gap: 8, marginLeft: 'auto', alignItems: 'center'}}>
          <select aria-label="Colour mode" value={mode} onChange={(e) => setMode(e.target.value)} style={{padding: 8, borderRadius: 8, border: '1px solid var(--color-border)'}}>
            <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
          </select>
          <select aria-label={tr('Language')} value={locale} onChange={(e) => setLocale(e.target.value)} style={{padding: 8, borderRadius: 8, border: '1px solid var(--color-border)'}}>
            {LOCALES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
          {showTabs ? <TabList value={tab} onChange={setTab}>
            <Tab value="home" label={tr('Home')} />
            <Tab value="setup" label={tr('Setup')} />
            <Tab value="designs" label={tr('Designs')} />
            <Tab value="products" label={tr('Products')} />
            <Tab value="bookings" label={tr('Bookings')} />
            <Tab value="reports" label={tr('Reports')} />
            <Tab value="quotes" label={tr('Quotes')} />
            <Tab value="crm" label={tr('Enquiries')} />
            <Tab value="contacts" label={tr('Contacts')} />
            <Tab value="permissions" label={tr('Permissions')} />
            <Tab value="social" label={tr('Social')} />
            <Tab value="media" label={tr('Marketing media')} />
          </TabList> : null}
          <select aria-label="Navigation layout" value={layout} onChange={(e) => setLayout(e.target.value)} style={{padding: 8, borderRadius: 8, border: '1px solid var(--color-border)'}}><option value="tabs">Top tabs</option><option value="sidebar">Sidebar</option></select>
          {onInstall ? <Button label={tr('Install app')} variant="secondary" onClick={onInstall} /> : null}
          <Button label={tr('Sign out')} variant="ghost" onClick={onSignOut} />
        </div>
      </div>
      <div style={{height: 4, background: brand.accent || '#c8f560', marginTop: 16}} />
    </header>
  );
}

function Login({onLogin, locale, setLocale, tr}: {onLogin: (token: string) => void; locale: string; setLocale: (v: string) => void; tr: (key: string) => string}) {
  const [slug, setSlug] = useState('pukeko-construction');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  async function submit() {
    setError('');
    try {
      const data = await useApi('')('/owner/auth/login', 'POST', {slug, email, password});
      onLogin(data.access_token);
    } catch (e) { setError(e instanceof Error ? e.message : 'Login failed'); }
  }
  return (
    <div style={{maxWidth: 420, margin: '10vh auto', padding: 24}}>
      <div style={{display: 'flex', justifyContent: 'flex-end'}}>
        <select aria-label={tr('Language')} value={locale} onChange={(e) => setLocale(e.target.value)} style={{padding: 8, borderRadius: 8, border: '1px solid var(--color-border)'}}>
          {LOCALES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select>
      </div>
      <Heading level={1}>Concierge</Heading>
      <p>Sign in to set up your business, generate marketing media and manage enquiries.</p>
      <TextInput label={tr('Business ID')} value={slug} onChange={setSlug} />
      <TextInput label={tr('Email')} type="email" value={email} onChange={setEmail} />
      <TextInput label={tr('Password')} type="password" value={password} onChange={setPassword} />
      <TranslationNote locale={locale} />
      <div style={{marginTop: 16}}><Button label={tr('Sign in')} variant="primary" onClick={submit} /></div>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}

function Setup({token, brand, setBrand}: {token: string; brand: Brand; setBrand: (b: Brand) => void}) {
  const api = useApi(token);
  const notify = useNotify();
  const [step, setStep] = useState(1);
  const [business, setBusiness] = useState<Business>({name: '', site_url: '', notify_email: '', notify_phone: '', public_key: ''});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [logo, setLogo] = useState<File | null>(null);

  useEffect(() => {
    api('/owner/onboarding').then((data) => {
      const b = data.business || {};
      setBusiness({name: b.name || '', site_url: b.site_url || '', notify_email: b.notify_email || '', notify_phone: b.notify_phone || '', public_key: b.public_key || ''});
    }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load setup'));
  }, [token]);

  async function save(fields: Record<string, unknown>, next: number, note: string) {
    setBusy(true); setStatus('');
    try {
      await api('/owner/onboarding/profile', 'PATCH', fields);
      setStatus(note); setStep(next);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Save failed'); }
    setBusy(false);
  }

  async function saveBrand() {
    setBusy(true); setStatus('');
    try {
      const payload: Brand = {name: brand.name, accent: brand.accent, contact: brand.contact};
      if (logo) payload.logo = await readRaw(logo);
      const saved = await api('/owner/media/brand', 'PUT', payload);
      setBrand({name: saved.name || '', accent: saved.accent || '#c8f560', contact: saved.contact || '', logo: saved.logo_data || brand.logo || null});
      setStatus('Branding saved. It now follows through to your media and portal.'); notify('Branding saved.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Save failed'); }
    setBusy(false);
  }

  async function importSite() {
    setBusy(true); setStatus('Reading your public pages… this can take up to a minute.');
    try {
      const result = await api('/owner/knowledge/import-website', 'POST');
      setStatus('Imported ' + (result.chunks || 0) + ' knowledge chunks from ' + (result.pages || 0) + ' pages.'); notify('Knowledge imported.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Import failed'); }
    setBusy(false);
  }

  const snippet = business.public_key ? '<script src="https://chat.trendibizz.com/widget.js" data-key="' + business.public_key + '" defer></script>' : '';

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Set up {business.name || 'your business'}</Heading>
      <p>A click-through setup. Every step is text; nothing plays audio. You can skip anything and return later.</p>
      <ol style={{display: 'flex', gap: 8, flexWrap: 'wrap', listStyle: 'none', padding: 0}}>
        {['Welcome', 'Business', 'Contact', 'Website', 'Branding', 'Finish'].map((label, index) => (
          <li key={label} style={{padding: '6px 12px', borderRadius: 999, border: '1px solid var(--color-border)', background: step === index + 1 ? 'var(--color-accent)' : 'transparent', color: step === index + 1 ? 'var(--color-on-accent)' : 'inherit', fontSize: 13}}>
            {index + 1}. {label}
          </li>
        ))}
      </ol>

      {step === 1 ? (
        <Card>
          <Heading level={2}>How Concierge works</Heading>
          <p>Website chat, email, SMS and phone enquiries come in. Concierge answers from your own business information, captures the contact, books agreed appointments and records everything in your CRM.</p>
          <p>You only need to provide your business details, a contact email and phone. Everything else can be skipped.</p>
          <Button label="Continue" variant="primary" onClick={() => setStep(2)} />
        </Card>
      ) : null}

      {step === 2 ? (
        <Card>
          <Heading level={2}>Your business</Heading>
          <TextInput label="Business name" value={business.name} onChange={(v) => setBusiness({...business, name: v})} />
          <TextInput label="Website" type="url" value={business.site_url} onChange={(v) => setBusiness({...business, site_url: v})} />
          <Button label={busy ? 'Saving…' : 'Save and continue'} variant="primary" onClick={() => save({name: business.name, site_url: business.site_url || null}, 3, 'Business saved.')} />
          <Button label="Skip" variant="ghost" onClick={() => setStep(3)} />
        </Card>
      ) : null}

      {step === 3 ? (
        <Card>
          <Heading level={2}>Your contact details</Heading>
          <p>New-enquiry alerts go here. Your replies are routed back into your own CRM.</p>
          <TextInput label="Notification email" type="email" value={business.notify_email} onChange={(v) => setBusiness({...business, notify_email: v})} />
          <TextInput label="Contact phone" type="tel" value={business.notify_phone} onChange={(v) => setBusiness({...business, notify_phone: v})} />
          <Button label={busy ? 'Saving…' : 'Save and continue'} variant="primary" onClick={() => save({notify_email: business.notify_email || null, notify_phone: business.notify_phone || null}, 4, 'Contact details saved.')} />
          <Button label="Skip" variant="ghost" onClick={() => setStep(4)} />
        </Card>
      ) : null}

      {step === 4 ? (
        <Card>
          <Heading level={2}>Bring in your website</Heading>
          <p>We read the public pages you own and turn them into the assistant's answers. You can re-run this any time.</p>
          <Button label={busy ? 'Reading…' : 'Import my website'} variant="primary" onClick={importSite} />
          <Button label="Continue" variant="ghost" onClick={() => setStep(5)} />
        </Card>
      ) : null}

      {step === 5 ? (
        <Card>
          <Heading level={2}>Your branding</Heading>
          <p>Your logo, name, contact line and accent colour follow through to your media and portal.</p>
          <TextInput label="Brand name" value={brand.name} onChange={(v) => setBrand({...brand, name: v})} />
          <TextInput label="Contact line" value={brand.contact} onChange={(v) => setBrand({...brand, contact: v})} />
          <TextInput label="Accent colour (hex)" value={brand.accent} onChange={(v) => setBrand({...brand, accent: v})} />
          <FileInput label="Logo" value={logo} onChange={(v) => setLogo((v as File) || null)} accept="image/*" />
          <Button label={busy ? 'Saving…' : 'Save branding'} variant="primary" onClick={saveBrand} />
          <Button label="Continue" variant="ghost" onClick={() => setStep(6)} />
        </Card>
      ) : null}

      {step === 6 ? (
        <Card>
          <Heading level={2}>You're ready</Heading>
          <p>Add this line to your website to show the chat window:</p>
          <TextArea label="Website embed code" value={snippet} onChange={() => {}} rows={3} />
          <Button label="Copy embed code" variant="secondary" onClick={() => { navigator.clipboard?.writeText(snippet); setStatus('Copied.'); notify('Embed code copied.'); }} />
          <p>Next: connect email, SMS, phone, social accounts and a calendar. Those live in the workspace and are enabled only after testing.</p>
        </Card>
      ) : null}

      <div style={{display: 'flex', gap: 8, marginTop: 16}}>
        {step > 1 ? <Button label="Back" variant="ghost" onClick={() => setStep(step - 1)} /> : null}
        {step < 6 ? <Button label="Next" variant="secondary" onClick={() => setStep(step + 1)} /> : null}
      </div>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}

function Invite({onToken}: {onToken: (token: string) => void}) {
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const token = location.hash.startsWith('#invite=') ? location.hash.slice(8) : '';
  async function submit() {
    setError('');
    if (password !== confirm) { setError('Passwords do not match.'); return; }
    try {
      const data = await useApi('')('/owner/auth/redeem', 'POST', {token, password});
      const login = await useApi('')('/owner/auth/login', 'POST', {slug: data.slug, email: data.email, password});
      history.replaceState(null, '', location.pathname);
      onToken(login.access_token);
    } catch (e) { setError(e instanceof Error ? e.message : 'Invitation failed'); }
  }
  return (
    <div style={{maxWidth: 420, margin: '10vh auto', padding: 24}}>
      <Heading level={1}>Welcome to Concierge</Heading>
      <p>Choose a password to open your private setup. It is a click-through setup; nothing plays audio.</p>
      <TextInput label="Password (12+ characters)" type="password" value={password} onChange={setPassword} />
      <TextInput label="Confirm password" type="password" value={confirm} onChange={setConfirm} />
      <div style={{marginTop: 16}}><Button label="Set password and continue" variant="primary" onClick={submit} /></div>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}


function money(cents: number, currency: string) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency: currency || 'NZD'}).format((cents || 0) / 100);
}

function Bookings({token}: {token: string}) {
  const api = useApi(token);
  const notify = useNotify();
  const [calendar, setCalendar] = useState<{configured?: boolean; connected?: boolean; provider?: string}>({});
  const [appointments, setAppointments] = useState<Record<string, unknown>[]>([]);
  const [role, setRole] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [slot, setSlot] = useState(30);
  const [hours, setHours] = useState<Record<string, {start: string; end: string; open: boolean}>>({
    mon: {start: '09:00', end: '17:00', open: true}, tue: {start: '09:00', end: '17:00', open: true},
    wed: {start: '09:00', end: '17:00', open: true}, thu: {start: '09:00', end: '17:00', open: true},
    fri: {start: '09:00', end: '17:00', open: true}, sat: {start: '09:00', end: '17:00', open: false},
    sun: {start: '09:00', end: '17:00', open: false},
  });
  const [ack, setAck] = useState(false);
  const [textback, setTextback] = useState<{enabled?: boolean; count_30d?: number; recoveries?: Record<string, unknown>[]}>({});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const days: Array<[string, string]> = [['mon','Monday'],['tue','Tuesday'],['wed','Wednesday'],['thu','Thursday'],['fri','Friday'],['sat','Saturday'],['sun','Sunday']];

  async function load() {
    try {
      const [cal, crm, onboarding, me, missed] = await Promise.all([
        api('/owner/calendar'), api('/owner/crm'), api('/owner/onboarding'), api('/owner/me'),
        api('/owner/missed-calls')]);
      setTextback(missed as {enabled?: boolean; count_30d?: number; recoveries?: Record<string, unknown>[]});
      setCalendar(cal as {configured?: boolean; connected?: boolean; provider?: string});
      setAppointments(((crm as {appointments?: Record<string, unknown>[]}).appointments || []));
      const business = (onboarding as {business?: Record<string, unknown>}).business || {};
      setEnabled(Boolean(business.native_booking));
      setSlot(Number(business.slot_minutes) || 30);
      const saved = (business.business_hours || {}) as Record<string, string[][]>;
      setHours((current) => {
        const next = {...current};
        for (const [key] of days) {
          const windows = saved[key];
          if (Array.isArray(windows) && windows[0]) {
            next[key] = {start: windows[0][0], end: windows[0][1], open: true};
          } else if (saved && Object.keys(saved).length) {
            next[key] = {...next[key], open: false};
          }
        }
        return next;
      });
      setRole((me as {role: string}).role);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load bookings'); }
  }
  useEffect(() => { load(); }, [token]);

  async function connectCalendar() {
    if (role !== 'owner') { setStatus('Only the business owner can connect the calendar.'); return; }
    const popup = window.open('about:blank', 'concierge-social-oauth', 'width=620,height=760');
    if (!popup) { setStatus('Allow popups for this page to connect Google Calendar.'); return; }
    try {
      const start = await api('/owner/calendar/start', 'POST') as {authorization_url: string; state: string};
      const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('concierge-social-oauth:' + start.state) : null;
      let finished = false;
      const finish = async (data: {state?: string; code?: string; error?: string}) => {
        if (finished || !data || data.state !== start.state) return;
        finished = true;
        channel?.close();
        try { popup.close(); } catch { /* ignore */ }
        if (data.error || !data.code) { setStatus('Calendar authorization was cancelled.'); return; }
        try {
          await api('/owner/calendar/finish', 'POST', {state: data.state, code: data.code});
          setStatus('Google Calendar connected.'); notify('Google Calendar connected.');
          await load();
        } catch (e) { setStatus(e instanceof Error ? e.message : 'Calendar connection failed'); }
      };
      if (channel) channel.onmessage = (event) => { void finish(event.data); };
      window.addEventListener('message', (event) => {
        if (event.origin === location.origin && event.data?.type === 'concierge-social-oauth') void finish(event.data);
      });
      popup.location.href = start.authorization_url;
      setStatus('Continue in the Google window.');
    } catch (e) {
      try { popup.close(); } catch { /* ignore */ }
      setStatus(e instanceof Error ? e.message : 'Calendar connection unavailable');
    }
  }

  async function saveBooking() {
    setBusy(true); setStatus('');
    try {
      const businessHours: Record<string, string[][]> = {};
      for (const [key] of days) if (hours[key]?.open) businessHours[key] = [[hours[key].start, hours[key].end]];
      await api('/owner/onboarding/profile', 'PATCH', {slot_minutes: Number(slot), business_hours: businessHours});
      if (enabled && !ack) throw new Error('Tick the acknowledgement before enabling booking.');
      await api('/owner/onboarding/native-booking', 'POST', {enabled, acknowledgement: ack});
      setStatus(enabled ? 'Booking enabled with these hours.' : 'Booking disabled.'); notify(enabled ? 'Booking enabled.' : 'Booking disabled.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save booking settings'); }
    setBusy(false);
  }

  async function saveTextback(next: boolean) {
    if (role !== 'owner') { setStatus('Only the business owner can change this.'); return; }
    try {
      await api('/owner/missed-calls/textback', 'PUT', {enabled: next});
      setTextback({...textback, enabled: next});
      setStatus(next ? 'Missed-call text-back is on.' : 'Missed-call text-back is off.');
      notify(next ? 'Missed-call text-back is on.' : 'Missed-call text-back is off.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save that setting'); }
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Bookings</Heading>
      <p>Connect the business calendar and choose when Concierge may book appointments.</p>
      <Card>
        <Heading level={2}>Google Calendar</Heading>
        <p>{calendar.connected ? 'Connected.' : calendar.configured ? 'Ready to connect this business’s calendar.' : 'Calendar connection is awaiting Trendi setup.'}</p>
        {calendar.configured && !calendar.connected ? <Button label="Connect Google Calendar" variant="primary" onClick={connectCalendar} /> : null}
        {calendar.connected ? <Button label="Disconnect" variant="ghost" onClick={async () => { try { await api('/owner/calendar', 'DELETE'); await load(); setStatus('Calendar disconnected.'); } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not disconnect'); } }} /> : null}
      </Card>

      <Card>
        <Heading level={2}>Booking rules</Heading>
        <label style={{display: 'block', margin: '8px 0'}}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Allow Concierge to book agreed appointments
        </label>
        <label style={{display: 'block', margin: '8px 0'}}>
          Appointment length (minutes)
          <input type="number" min={5} max={240} value={slot} onChange={(e) => setSlot(Number(e.target.value) || 30)} style={{display: 'block', padding: 8}} />
        </label>
        <p><strong>Opening hours</strong></p>
        {days.map(([key, label]) => (
          <div key={key} style={{display: 'flex', gap: 8, alignItems: 'center', margin: '6px 0', flexWrap: 'wrap'}}>
            <label style={{minWidth: 90}}><input type="checkbox" checked={hours[key].open} onChange={(e) => setHours({...hours, [key]: {...hours[key], open: e.target.checked}})} /> {label}</label>
            <input aria-label={label + ' start'} type="time" value={hours[key].start} disabled={!hours[key].open} onChange={(e) => setHours({...hours, [key]: {...hours[key], start: e.target.value}})} />
            <input aria-label={label + ' end'} type="time" value={hours[key].end} disabled={!hours[key].open} onChange={(e) => setHours({...hours, [key]: {...hours[key], end: e.target.value}})} />
          </div>
        ))}
        <label style={{display: 'block', margin: '10px 0'}}>
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> The hours and rules are correct, and Concierge may book appointments.
        </label>
        <Button label={busy ? 'Saving…' : 'Save booking settings'} variant="primary" onClick={saveBooking} />
      </Card>

      <Card>
        <Heading level={2}>Missed-call text-back</Heading>
        <p>
          When someone calls and hangs up before Concierge can help, we text them once with your
          booking link and record it as an enquiry — so the job is not lost. This is included;
          you can switch it off here.
        </p>
        <label style={{display: 'block', margin: '8px 0'}}>
          <input type="checkbox" checked={textback.enabled !== false}
                 onChange={(e) => saveTextback(e.target.checked)} /> Text back callers we miss
        </label>
        <p><strong>{textback.count_30d || 0}</strong> missed caller{(Number(textback.count_30d) === 1) ? '' : 's'} texted back in the last 30 days.</p>
        {(textback.recoveries || []).slice(0, 5).map((row, index) => (
          <p key={index} style={{margin: '4px 0'}}>
            {String(row.contact || '')} · {String(row.status || '')} · {String(row.created_at || '').slice(0, 16)}
          </p>
        ))}
      </Card>

      <Heading level={2}>Appointments</Heading>
      {appointments.length ? appointments.map((appointment, index) => (
        <Card key={index}>
          <strong>{String(appointment.title || appointment.name || 'Appointment')}</strong>
          <p>{String(appointment.start_at || appointment.start || appointment.when || '')}</p>
        </Card>
      )) : <p>No appointments booked yet.</p>}
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}

function Reports({token}: {token: string}) {
  const api = useApi(token);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [status, setStatus] = useState('');

  useEffect(() => {
    Promise.all([api('/owner/crm'), api('/owner/crm/quotations'), api('/owner/social/posts'), api('/owner/media/assets')])
      .then(([crm, q, p, a]) => {
        setLeads(((crm as {leads?: Lead[]}).leads || []));
        setQuotes(q as Quote[]); setPosts(p as Post[]); setAssets(a as Asset[]);
      }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load reports'));
  }, [token]);

  const quoted = quotes.filter((quote) => ['reviewed', 'accepted'].includes(quote.status)).reduce((sum, quote) => sum + quote.total_cents, 0);
  const metrics = [
    ['Enquiries', leads.length],
    ['Quotations', quotes.length],
    ['Quoted value', money(quoted, 'NZD')],
    ['Social posts', posts.length],
    ['Media assets', assets.length],
  ] as Array<[string, string | number]>;

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Reports</Heading>
      <p>A simple view of the work coming in and going out.</p>
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))'}}>
        {metrics.map(([label, value]) => (
          <Card key={label}><strong style={{fontSize: 28}}>{value}</strong><p>{label}</p></Card>
        ))}
      </div>
      <Heading level={2}>Quotations by status</Heading>
      {['draft', 'reviewed', 'accepted', 'declined', 'void'].map((state) => (
        <p key={state}>{state}: {quotes.filter((quote) => quote.status === state).length}</p>
      ))}
      <Heading level={2}>Latest enquiries</Heading>
      {leads.slice(0, 5).map((lead) => <p key={lead.id}>{lead.name || lead.email || 'Enquiry'} · {lead.status}</p>)}
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


function Admin() {
  const [token, setToken] = useState(() => sessionStorage.getItem('adminToken') || '');
  const [tenants, setTenants] = useState<Record<string, unknown>[]>([]);
  const [status, setStatus] = useState<{counts?: Record<string, number>; backups?: Array<{name: string; bytes: number; modified: number}>}>({});
  const [error, setError] = useState('');

  async function load() {
    setError('');
    const headers = {'X-Admin-Token': token, 'Accept': 'application/json'};
    try {
      const [t, s] = await Promise.all([
        fetch('/admin/tenants', {headers}).then((r) => r.ok ? r.json() : Promise.reject(new Error('Admin token rejected'))),
        fetch('/admin/status', {headers}).then((r) => r.ok ? r.json() : Promise.reject(new Error('Admin status unavailable'))),
      ]);
      setTenants(t as Record<string, unknown>[]); setStatus(s); sessionStorage.setItem('adminToken', token);
    } catch (e) { setError(e instanceof Error ? e.message : 'Admin request failed'); }
  }

  useEffect(() => { if (token) load(); }, []);

  if (!token) {
    return (
      <div style={{maxWidth: 420, margin: '10vh auto', padding: 24}}>
        <Heading level={1}>Trendi admin</Heading>
        <p>Internal console. The admin token is required.</p>
        <TextInput label="Admin token" type="password" value={token} onChange={setToken} />
        <div style={{marginTop: 16}}><Button label="Open console" variant="primary" onClick={load} /></div>
        {error ? <p role="alert">{error}</p> : null}
      </div>
    );
  }

  const counts = status.counts || {};
  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: 24}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 12}}>
        <Heading level={1}>Trendi admin</Heading>
        <Button label="Refresh" variant="secondary" onClick={load} />
        <Button label="Sign out" variant="ghost" onClick={() => { sessionStorage.removeItem('adminToken'); setToken(''); }} />
      </div>
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', marginBottom: 24}}>
        {Object.entries(counts).map(([key, value]) => <Card key={key}><strong style={{fontSize: 24}}>{key === 'database_bytes' ? Math.round(Number(value) / 1048576) + ' MB' : value}</strong><p>{key.replaceAll('_', ' ')}</p></Card>)}
      </div>
      <Heading level={2}>Tenants</Heading>
      <div style={{display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))'}}>
        {tenants.map((tenant, index) => (
          <Card key={index}>
            <strong>{String(tenant.name || tenant.slug)}</strong>
            <p>{String(tenant.slug || '')}</p>
            <p>Phone: {tenant.phone_enabled ? 'enabled' : 'off'}</p>
          </Card>
        ))}
      </div>
      <Heading level={2}>Backups</Heading>
      {status.backups?.length ? status.backups.map((backup) => (
        <p key={backup.name}>{backup.name} · {Math.round(backup.bytes / 1048576)} MB · {new Date(backup.modified * 1000).toLocaleString()}</p>
      )) : <p>No backups found.</p>}
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}


function useDomTranslation(locale: string, dictionary: Record<string, string>) {
  useEffect(() => {
    if (locale === 'en' || !dictionary) return;
    const translate = () => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent || ['SCRIPT', 'STYLE', 'CODE', 'TEXTAREA', 'INPUT'].includes(parent.tagName)) continue;
        const value = node.nodeValue || '';
        const trimmed = value.trim();
        const translated = dictionary[trimmed];
        if (translated && translated !== trimmed) node.nodeValue = value.replace(trimmed, translated);
      }
      document.querySelectorAll('[placeholder], [aria-label], [title]').forEach((element) => {
        for (const attribute of ['placeholder', 'aria-label', 'title']) {
          const value = element.getAttribute(attribute);
          if (value && dictionary[value.trim()]) element.setAttribute(attribute, dictionary[value.trim()]);
        }
      });
    };
    translate();
    let timer: number | undefined;
    const observer = new MutationObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(translate, 60);
    });
    observer.observe(document.body, {childList: true, subtree: true, characterData: true});
    return () => { observer.disconnect(); window.clearTimeout(timer); };
  }, [locale, dictionary]);
}

function Shell() {
  const [token, setToken] = useState('');
  const [tab, setTab] = useState('home');
  const [brand, setBrand] = useState<Brand>({name: '', accent: '#c8f560', contact: ''});
  const [installEvent, setInstallEvent] = useState<Event | null>(null);
  const [locale, setLocaleState] = useState(initialLocale);
  const [catalog, setCatalog] = useState<Record<string, string>>(en);
  const [navStrings, setNavStrings] = useState<Record<string, string>>({});
  const [copyStrings, setCopyStrings] = useState<Record<string, string>>({});
  const [mode, setModeState] = useState(() => localStorage.getItem('concierge.mode') || 'system');
  const [layout, setLayoutState] = useState(() => new URLSearchParams(location.search).get('layout') || localStorage.getItem('concierge.layout') || 'sidebar');
  function setLayout(value: string) { setLayoutState(value); localStorage.setItem('concierge.layout', value); }
  function setMode(value: string) { setModeState(value); localStorage.setItem('concierge.mode', value); }
  const tr = (key: string) => navStrings[key] || key;
  useDomTranslation(locale, copyStrings);
  function setLocale(value: string) { setLocaleState(value); localStorage.setItem('concierge.locale', value); }
  useEffect(() => {
    const loader = localeLoaders['./locales/' + locale + '.json'];
    if (loader) loader().then((module) => setCatalog(module.default)).catch(() => setCatalog(en));
    else setCatalog(en);
  }, [locale]);
  useEffect(() => {
    const navLoader = navLoaders['./i18n/nav/' + locale + '.json'];
    const copyLoader = copyLoaders['./i18n/copy/' + locale + '.json'];
    Promise.all([
      navLoader ? navLoader().then((m) => m.default) : Promise.resolve({}),
      copyLoader ? copyLoader().then((m) => m.default) : Promise.resolve({}),
    ]).then(([nav, copy]) => { setNavStrings(nav); setCopyStrings(copy); }).catch(() => undefined);
  }, [locale]);
  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale.startsWith('ar') || locale.startsWith('he') ? 'rtl' : 'ltr';
  }, [locale]);
  useEffect(() => {
    if (localStorage.getItem('concierge.locale') || new URLSearchParams(location.search).get('lang')) return;
    api('/owner/locale').then((data) => { const suggested = (data as {locale?: string}).locale; if (suggested && hasLocale(suggested)) setLocaleState(suggested); }).catch(() => undefined);
  }, []);
  const theme = useMemo(() => defineTheme({name: 'tenant-' + (brand.name || 'concierge'), extends: neutralTheme, tokens: {'--color-accent': brand.accent || '#c8f560', '--color-on-accent': '#101408'}}), [brand.name, brand.accent]);
  const api = useApi(token);

  useEffect(() => {
    document.title = brand.name ? brand.name + ' — Concierge' : 'Concierge';
  }, [brand.name]);

  useEffect(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/studio/sw.js').catch(() => undefined);
    const handler = (event: Event) => { event.preventDefault(); setInstallEvent(event); };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  useEffect(() => {
    if (!token) return;
    api('/owner/media/brand').then((b) => setBrand({name: b.name || '', accent: b.accent || '#c8f560', contact: b.contact || '', logo: b.logo_data || null})).catch(() => undefined);
  }, [token]);

  if (!token) {
    return (
      <Theme theme={theme}>
        <InternationalizationProvider locale={locale} messages={{...CATALOGS, [locale]: catalog}}>
          {location.hash.startsWith('#invite=') ? <Invite onToken={setToken} /> : <Login onLogin={setToken} locale={locale} setLocale={setLocale} tr={tr} />}
        </InternationalizationProvider>
      </Theme>
    );
  }

  const content = (
    <>
      <TranslationNote locale={locale} />
      {tab === 'home' ? <Suspense fallback={<p style={{padding: 24}}>Loading dashboard…</p>}><Home token={token} brand={brand} /></Suspense> : tab === 'setup' ? <Setup token={token} brand={brand} setBrand={setBrand} /> : tab === 'designs' ? <Suspense fallback={<p style={{padding: 24}}>Loading designs…</p>}><Designs token={token} /></Suspense> : tab === 'products' ? <Suspense fallback={<p style={{padding: 24}}>Loading products…</p>}><ProductsPage token={token} /></Suspense> : tab === 'bookings' ? <Bookings token={token} /> : tab === 'reports' ? <Reports token={token} /> : tab === 'quotes' ? <Suspense fallback={<p style={{padding: 24}}>Loading quotes…</p>}><Quotes token={token} brand={brand} /></Suspense> : tab === 'crm' ? <Suspense fallback={<p style={{padding: 24}}>Loading enquiries…</p>}><Crm token={token} /></Suspense> : tab === 'contacts' ? <Suspense fallback={<p style={{padding: 24}}>Loading contacts…</p>}><Contacts token={token} /></Suspense> : tab === 'permissions' ? <Suspense fallback={<p style={{padding: 24}}>Loading permissions…</p>}><PermissionsPage token={token} /></Suspense> : tab === 'social' ? <Suspense fallback={<p style={{padding: 24}}>Loading social…</p>}><Social token={token} brand={brand} /></Suspense> : <Suspense fallback={<p style={{padding: 24}}>Loading media…</p>}><Media token={token} brand={brand} setBrand={setBrand} /></Suspense>}
    </>
  );
  const header = (
    <BrandHeader brand={brand} tab={tab} setTab={setTab} onSignOut={() => setToken('')} onInstall={installEvent ? () => { (installEvent as unknown as {prompt: () => void}).prompt(); setInstallEvent(null); } : undefined} locale={locale} setLocale={setLocale} tr={tr} mode={mode} setMode={setMode} showTabs={layout === 'tabs'} layout={layout} setLayout={setLayout} />
  );
  const sidebar = (
    <SideNav>
      <SideNavSection title={tr('Workspace')}>
        <SideNavItem label={tr('Home')} isSelected={tab === 'home'} onClick={() => setTab('home')} />
        <SideNavItem label={tr('Setup')} isSelected={tab === 'setup'} onClick={() => setTab('setup')} />
      </SideNavSection>
      <SideNavSection title={tr('Customers')}>
        <SideNavItem label={tr('Enquiries')} isSelected={tab === 'crm'} onClick={() => setTab('crm')} />
        <SideNavItem label={tr('Contacts')} isSelected={tab === 'contacts'} onClick={() => setTab('contacts')} />
        <SideNavItem label={tr('Bookings')} isSelected={tab === 'bookings'} onClick={() => setTab('bookings')} />
      </SideNavSection>
      <SideNavSection title={tr('Revenue')}>
        <SideNavItem label={tr('Quotes')} isSelected={tab === 'quotes'} onClick={() => setTab('quotes')} />
        <SideNavItem label={tr('Products')} isSelected={tab === 'products'} onClick={() => setTab('products')} />
        <SideNavItem label={tr('Reports')} isSelected={tab === 'reports'} onClick={() => setTab('reports')} />
      </SideNavSection>
      <SideNavSection title={tr('Marketing')}>
        <SideNavItem label={tr('Social')} isSelected={tab === 'social'} onClick={() => setTab('social')} />
        <SideNavItem label={tr('Marketing media')} isSelected={tab === 'media'} onClick={() => setTab('media')} />
        <SideNavItem label={tr('Designs')} isSelected={tab === 'designs'} onClick={() => setTab('designs')} />
      </SideNavSection>
    </SideNav>
  );

  return (
    <Theme theme={theme} mode={mode as 'light' | 'dark' | 'system'}>
    <NotifyProvider>
    <InternationalizationProvider locale={locale} messages={{...CATALOGS, [locale]: catalog}}>
    {layout === 'sidebar' ? (
      <AppShell topNav={header} sideNav={sidebar} mobileNav={{hasToggle: true}} contentPadding={0} height="auto">{content}</AppShell>
    ) : (
      <div>{header}{content}</div>
    )}
    </InternationalizationProvider>
    </NotifyProvider>
    </Theme>
  );
}

export default function App() {
  return location.hash === '#admin' ? <Theme theme={neutralTheme}><Admin /></Theme> : <Shell />;
}
