import {lazy, Suspense, useEffect, useMemo, useRef, useState} from 'react';
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
import {Badge} from '@astryxdesign/core/Badge';
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


function ErrorNote({message}: {message: string}) {
  const ref = useRef<HTMLParagraphElement>(null);
  // Bring the message into view: an error below the fold, or in a long form, is an error nobody sees.
  useEffect(() => { ref.current?.scrollIntoView({block: 'nearest', behavior: 'smooth'}); }, [message]);
  return (
    <p ref={ref} role="alert" className="error-note"><strong>Problem:</strong> {message}</p>
  );
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
    if (response.status === 401 && token) window.dispatchEvent(new Event('concierge:sign-out'));
    if (!response.ok) {
      // FastAPI answers a validation error with a list of objects; never let a page print that as "[object Object]".
      const detail = typeof data.detail === 'string' ? data.detail
        : Array.isArray(data.detail) ? data.detail.map((d: {msg?: string}) => d.msg || 'A detail is not valid.').join(' ') : '';
      throw new Error(detail || 'Request failed (' + response.status + ')');
    }
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

function RequestLink({title, intro, note}: {title: string; intro: string; note?: string}) {
  const api = useApi('');
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit() {
    if (!email.trim()) { setError('Enter the email address your invite came to.'); return; }
    setBusy(true); setError('');
    try {
      await api('/owner/auth/link', 'POST', {email: email.trim()});
      setSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not send the link');
    }
    setBusy(false);
  }

  return (
    <div style={{maxWidth: 460, margin: '10vh auto', padding: 24}}>
      <Heading level={1}>{title}</Heading>
      <p>{intro}</p>
      {note ? <p>{note}</p> : null}
      {sent ? (
        <Card>
          <Heading level={2}>Check your email</Heading>
          <p>If {email.trim()} has an account, a one-click link is on its way. It works once and expires in 24 hours.</p>
          <p>Nothing arrived? Check the spam folder, then try again.</p>
          <Button label="Send it again" variant="secondary" onClick={() => { setSent(false); }} />
        </Card>
      ) : (
        <>
          <TextInput label="Email" type="email" value={email} onChange={setEmail} />
          <div style={{marginTop: 16}}>
            <Button label={busy ? 'Sending…' : 'Email me a sign-in link'} variant="primary" onClick={submit} />
          </div>
          <p style={{fontSize: 13, opacity: 0.75}}>No password to remember: the link signs you in.</p>
        </>
      )}
      {error ? <ErrorNote message={error} /> : null}
    </div>
  );
}

function Login({locale, setLocale, tr}: {locale: string; setLocale: (v: string) => void; tr: (key: string) => string}) {
  return (
    <div>
      <div style={{display: 'flex', justifyContent: 'flex-end', padding: '16px 24px 0'}}>
        <select aria-label={tr('Language')} value={locale} onChange={(e) => setLocale(e.target.value)} style={{padding: 8, borderRadius: 8, border: '1px solid var(--color-border)'}}>
          {LOCALES.map(([code, label]) => <option key={code} value={code}>{label}</option>)}
        </select>
      </div>
      <RequestLink
        title="Concierge"
        intro="Sign in to set up your business, generate marketing media and manage enquiries."
      />
      <div style={{maxWidth: 460, margin: '-6vh auto 0', padding: '0 24px 48px'}}>
        <TranslationNote locale={locale} />
      </div>
    </div>
  );
}

function Invite({onToken}: {onToken: (token: string) => void}) {
  const token = location.hash.startsWith('#invite=') ? location.hash.slice(8) : '';
  const api = useApi('');
  const [failed, setFailed] = useState(!token);
  const [problem, setProblem] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) { setFailed(true); return; }
    let cancelled = false;
    api('/owner/auth/invite', 'POST', {token})
      .then((data) => {
        if (cancelled) return;
        // The link is spent: drop it from the address bar so a refresh cannot replay it.
        history.replaceState(null, '', location.pathname + location.search);
        sessionStorage.setItem('concierge.startAtSetup', '1');
        onToken(data.access_token);
      })
      .catch((e) => {
        if (cancelled) return;
        setFailed(true);
        setProblem(e instanceof Error ? e.message : 'This link has expired.');
      });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, attempt]);

  if (!failed) {
    return (
      <div style={{maxWidth: 460, margin: '10vh auto', padding: 24, textAlign: 'center'}}>
        <Heading level={1}>Welcome to Concierge</Heading>
        <p>Signing you in…</p>
      </div>
    );
  }
  return (
    <div>
      <RequestLink
        title="Welcome to Concierge"
        intro="This link has expired or has already been used."
        note="Enter your email and we will send you a fresh one-click link. No password needed."
      />
      {problem ? <div style={{maxWidth: 460, margin: '0 auto', padding: '0 24px 48px'}}><ErrorNote message={problem} /></div> : null}
      <div style={{maxWidth: 460, margin: '0 auto', padding: '0 24px 48px'}}>
        <Button label="Try this link again" variant="ghost" onClick={() => { setFailed(false); setProblem(''); setAttempt(attempt + 1); }} />
      </div>
    </div>
  );
}

type Capability = {
  key: string;
  channels: string[];
  title: string;
  what: string;
  data: string;
  undo: string;
};

// One card per thing a customer might want switched on, in their words. Each card says what we
// will do, what data it touches, and how to undo it, and the customer's own click is what grants
// it — the same rule the Permissions tab follows, just without making them hunt for that tab.
const CAPABILITIES: Capability[] = [
  {key: 'email', channels: ['email_read', 'email_send'], title: 'Read and reply to my email',
   what: 'Concierge reads enquiries sent to your business address and drafts the replies for you to approve.',
   data: 'The text of emails sent to your business address.',
   undo: 'Withdraw it here at any time. Nothing is deleted.'},
  {key: 'phone', channels: ['telephone'], title: 'Answer my phone',
   what: 'Concierge answers calls on the number you point at Trendi and takes a message.',
   data: 'What the caller says, and any number they give.',
   undo: 'Withdraw it and calls stop being answered at once.'},
  {key: 'recording', channels: ['call_recording'], title: 'Record calls',
   what: 'Callers hear "Our calls are recorded for quality and training purposes" before recording starts, and recording stops if they object.',
   data: 'The audio of the call and its transcript.',
   undo: 'Withdraw it and new calls are not recorded.'},
  {key: 'texts', channels: ['sms_read', 'sms_send'], title: 'Text customers',
   what: 'Concierge reads texts sent to your business number and can reply and send reminders.',
   data: 'Texts to and from your business number.',
   undo: 'Withdraw it at once.'},
  {key: 'social', channels: ['social'], title: 'Post to my social accounts',
   what: 'Drafts are published only after you approve each one.',
   data: 'The posts you approve.',
   undo: 'Withdraw it at once.'},
];

function Capabilities({token, onChanged}: {token: string; onChanged?: () => void}) {
  const api = useApi(token);
  const [auth, setAuth] = useState<Record<string, {authorized?: boolean}>>({});
  const [busy, setBusy] = useState('');
  const [note, setNote] = useState('');
  const [problem, setProblem] = useState('');

  const load = () => api('/owner/onboarding/authorizations').then(setAuth).catch(() => undefined);
  useEffect(() => { void load(); }, [token]);

  const on = (cap: Capability) => cap.channels.every((channel) => auth[channel]?.authorized === true);
  const allowed = CAPABILITIES.filter(on).length;

  async function decide(cap: Capability, allow: boolean) {
    setBusy(cap.key); setProblem(''); setNote('');
    try {
      for (const channel of cap.channels) {
        await api('/owner/onboarding/authorizations', 'POST',
                  {channel, authorized: allow, acknowledgement: true});
      }
      await load();
      setNote(allow ? 'Allowed: ' + cap.title + '.' : 'Withdrawn: ' + cap.title + '.');
      onChanged?.();
    } catch (e) {
      setProblem(e instanceof Error ? e.message : 'Could not save that permission');
    }
    setBusy('');
  }

  return (
    <div style={{marginTop: 24}}>
      <Heading level={3}>What should Concierge do for you?</Heading>
      <p>We can only do what you allow. {allowed} of {CAPABILITIES.length} are switched on.</p>
      {CAPABILITIES.map((cap) => {
        const granted = on(cap);
        return (
          <div key={cap.key} style={{border: '1px solid var(--color-border)', borderRadius: 10, padding: 14, marginBottom: 10, background: granted ? 'rgba(34,197,94,0.08)' : 'transparent'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12}}>
              <strong>{cap.title}</strong>
              <span style={{fontSize: 13, opacity: 0.8}}>{granted ? 'Switched on' : 'Not allowed'}</span>
            </div>
            <p style={{margin: '6px 0 2px', fontSize: 14}}>{cap.what}</p>
            <p style={{margin: 0, fontSize: 13, opacity: 0.75}}>It uses: {cap.data} {cap.undo}</p>
            <div style={{marginTop: 8}}>
              <Button
                label={busy === cap.key ? 'Saving…' : granted ? 'Withdraw this' : 'Yes, allow this'}
                variant={granted ? 'ghost' : 'primary'}
                onClick={() => decide(cap, !granted)}
              />
            </div>
          </div>
        );
      })}
      {note ? <p role="status" style={{fontSize: 14}}>{note}</p> : null}
      {problem ? <ErrorNote message={problem} /> : null}
      <p style={{fontSize: 13, opacity: 0.75}}>
        You can change any of these later in the Permissions tab. Withdrawing takes effect immediately.
      </p>
    </div>
  );
}

type Suggestion = {
  website: string;
  name: string;
  logo: {data: string; bytes: number; rendered_from_svg: boolean; text_font_risk?: boolean; font_substituted?: boolean; note?: string} | null;
  logo_alternatives: Array<{source?: string; data?: string; why?: string; text_font_risk?: boolean; font_substituted?: boolean; note?: string}>;
  accent: string;
  accent_source: string;
  contact: {phone: string; email: string; line: string};
  socials: Record<string, string>;
  platform: {kind: string; generator: string; elementor: boolean; install_hint: string};
  timezone: string;
  country_code: string;
  notes: string[];
};

// Offered first, never a hex box: the customer picks a colour, they do not type one.
const ACCENT_PRESETS = ['#7142d6', '#c8f560', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#111827', '#db2777'];
const TIMEZONES: Array<[string, string]> = [
  ['Pacific/Auckland', 'New Zealand (Auckland)'],
  ['Australia/Sydney', 'Australia (Sydney)'],
  ['Europe/London', 'United Kingdom (London)'],
  ['America/New_York', 'United States (Eastern)'],
  ['America/Chicago', 'United States (Central)'],
  ['America/Los_Angeles', 'United States (Pacific)'],
  ['Asia/Singapore', 'Singapore'],
  ['UTC', 'UTC'],
];

function Setup({token, brand, setBrand, onDone}: {token: string; brand: Brand; setBrand: (b: Brand) => void; onDone: () => void}) {
  const api = useApi(token);
  const notify = useNotify();
  const [step, setStep] = useState(1);
  const [business, setBusiness] = useState<Business>({name: '', site_url: '', notify_email: '', notify_phone: '', public_key: ''});
  const [slug, setSlug] = useState('');
  const [status, setStatus] = useState('');
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  const [logo, setLogo] = useState<File | null>(null);
  // The review screen: one page of what we read, everything editable, one confirmation.
  const [website, setWebsite] = useState('');
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [reading, setReading] = useState(false);
  const [name, setName] = useState('');
  const [accent, setAccent] = useState('#c8f560');
  const [contact, setContact] = useState('');
  const [timezone, setTimezone] = useState('Pacific/Auckland');
  const [logoData, setLogoData] = useState<string | null>(null);
  const [install, setInstall] = useState<{found: boolean; detail: string} | null>(null);
  const [checkingSite, setCheckingSite] = useState(false);

  useEffect(() => {
    api('/owner/onboarding').then((data) => {
      const b = data.business || {};
      setBusiness({name: b.name || '', site_url: b.site_url || '', notify_email: b.notify_email || '', notify_phone: b.notify_phone || '', public_key: b.public_key || ''});
      setSlug(b.slug || '');
      setWebsite(b.site_url || '');
      setName(b.name || '');
      setTimezone(b.timezone || 'Pacific/Auckland');
      setAccent(brand.accent || '#c8f560');
      setContact(brand.contact || '');
    }).catch((e) => setProblem(e instanceof Error ? e.message : 'Could not load setup'));
  }, [token]);

  async function readWebsite() {
    const address = website.trim();
    if (!address) { setProblem('Enter your website address first, for example yourbusiness.co.nz'); return; }
    setReading(true); setProblem(''); setStatus('Reading your public pages. This takes a few seconds.');
    try {
      const found: Suggestion = await api('/owner/onboarding/brand-suggestion?website=' + encodeURIComponent(address));
      setSuggestion(found);
      setName(found.name || business.name || '');
      setAccent(found.accent || '#c8f560');
      setContact(found.contact?.line || '');
      setTimezone(found.timezone || timezone);
      setLogoData(found.logo?.data || null);
      setStatus(found.logo ? '' : 'We could not find a logo you can use. You can upload one below.');
    } catch (e) {
      setProblem(e instanceof Error ? e.message : 'Could not read that website');
      setStatus('');
    }
    setReading(false);
  }

  async function saveEverything() {
    const chosen = name.trim();
    if (!chosen) { setProblem('Enter your business name.'); return; }
    setBusy(true); setProblem('');
    try {
      const fields: Record<string, unknown> = {name: chosen, site_url: website.trim() || null, timezone};
      const email = suggestion?.contact?.email || '';
      const phone = suggestion?.contact?.phone || '';
      if (email) fields.notify_email = email;
      if (phone) fields.notify_phone = phone;
      await api('/owner/onboarding/profile', 'PATCH', fields);
      const finalLogo = logoData || (logo ? await readRaw(logo) : null);
      const saved = await api('/owner/media/brand', 'PUT', {name: chosen, accent, contact: contact.trim(), ...(finalLogo ? {logo: finalLogo} : {})});
      setBrand({name: saved.name || chosen, accent: saved.accent || accent, contact: saved.contact || contact, logo: saved.logo_data || finalLogo});
      setBusiness({...business, name: chosen, site_url: website.trim(), notify_email: email || business.notify_email, notify_phone: phone || business.notify_phone});
      setStatus('Saved. This is how your business will appear.'); notify('Business saved.');
      setStep(3);
    } catch (e) { setProblem(e instanceof Error ? e.message : 'Save failed'); }
    setBusy(false);
  }

  async function checkLiveSite() {
    setCheckingSite(true); setProblem('');
    try {
      setInstall(await api('/owner/onboarding/install-check?website=' + encodeURIComponent(website.trim())));
    } catch (e) { setProblem(e instanceof Error ? e.message : 'Could not read your website'); }
    setCheckingSite(false);
  }

  const snippet = business.public_key ? '<script src="https://chat.trendibizz.com/widget.js" data-key="' + business.public_key + '" defer></script>' : '';
  const hosted = slug ? 'https://chat.trendibizz.com/demo/' + slug : '';
  const platform = suggestion?.platform;
  const handOff = platform ? platform.install_hint === 'Email this to my web person' : false;
  const mailBody = 'Please add our chat window to our website by pasting this before </body>:\n\n' + snippet + '\n\nThis shows a chat window where customers can ask questions and leave their details. It is provided by Trendi Concierge (' + (business.name || name) + ').';
  const alternatives = (suggestion?.logo_alternatives || []).filter((item) => item.data);

  function accentButton(colour: string) {
    const selected = accent.toLowerCase() === colour.toLowerCase();
    return (
      <button key={colour} type="button" onClick={() => setAccent(colour)} aria-label={'Use ' + colour}
        aria-pressed={selected}
        style={{width: 36, height: 36, borderRadius: 999, border: selected ? '3px solid var(--color-text, #111)' : '1px solid var(--color-border)', background: colour, cursor: 'pointer'}} />
    );
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Set up {name || business.name || 'your business'}</Heading>
      <p>Give us your website and confirm what we found. You do not need to type what we can read.</p>
      <ol style={{display: 'flex', gap: 8, flexWrap: 'wrap', listStyle: 'none', padding: 0}}>
        {['Welcome', 'Your business', 'Finish'].map((label, index) => (
          <li key={label} style={{padding: '6px 12px', borderRadius: 999, border: '1px solid var(--color-border)', background: step === index + 1 ? 'var(--color-accent)' : 'transparent', color: step === index + 1 ? 'var(--color-on-accent)' : 'inherit', fontSize: 13}}>
            {index + 1}. {label}
          </li>
        ))}
      </ol>

      {step === 1 ? (
        <Card>
          <Heading level={2}>How Concierge works</Heading>
          <p>Website chat, email, SMS and phone enquiries come in. Concierge answers from your own business information, captures the contact, books agreed appointments and records everything in your CRM.</p>
          <p>You give us your website and say yes. We read your public pages, show you what we understood, and you confirm it. Anything we could not find is the only thing we ask.</p>
          <Button label="Continue" variant="primary" onClick={() => setStep(2)} />
        </Card>
      ) : null}

      {step === 2 ? (
        <Card>
          <Heading level={2}>Your business</Heading>
          <TextInput label="Website" type="url" placeholder="yourbusiness.co.nz" value={website} onChange={setWebsite} />
          <div style={{display: 'flex', gap: 8, marginTop: 8}}>
            <Button label={reading ? 'Reading…' : 'Check my website'} variant="primary" onClick={readWebsite} />
          </div>

          {suggestion ? (
            <div style={{marginTop: 24}}>
              <Heading level={3}>Here is your business as we understand it</Heading>
              <p>Change anything that is wrong. This is saved only when you press "Looks right".</p>

              <div style={{display: 'flex', gap: 16, alignItems: 'center', margin: '16px 0'}}>
                {logoData
                  ? <img src={logoData} alt="Your logo" style={{maxHeight: 96, maxWidth: 320, objectFit: 'contain', background: '#fff', padding: 8, borderRadius: 8, border: '1px solid var(--color-border)'}} />
                  : <div style={{width: 160, height: 96, borderRadius: 8, border: '1px dashed var(--color-border)', display: 'grid', placeItems: 'center', fontSize: 13}}>No logo yet</div>}
                <div>
                  {alternatives.length ? <p style={{fontSize: 13, marginBottom: 6}}>Another image from your site:</p> : null}
                  <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                    {alternatives.map((item, index) => (
                      <button key={index} type="button" onClick={() => setLogoData(item.data || null)} title={item.note || 'Use this image'}
                        style={{padding: 4, borderRadius: 8, border: logoData === item.data ? '2px solid var(--color-text, #111)' : '1px solid var(--color-border)', background: '#fff', cursor: 'pointer'}}>
                        <img src={item.data} alt={'Logo option ' + (index + 1)} style={{height: 40, maxWidth: 120, objectFit: 'contain'}} />
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <TextInput label="Business name" value={name} onChange={setName} />
              <TextInput label="Contact line" value={contact} onChange={setContact} />

              <p style={{marginTop: 16, marginBottom: 6, fontSize: 14}}>Brand colour</p>
              <div style={{display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap'}}>
                {ACCENT_PRESETS.map(accentButton)}
                <input type="color" value={accent} onChange={(event) => setAccent(event.target.value)}
                  aria-label="Pick your own brand colour"
                  style={{width: 40, height: 36, padding: 0, border: '1px solid var(--color-border)', borderRadius: 8, background: 'transparent', cursor: 'pointer'}} />
              </div>
              <p style={{fontSize: 13, opacity: 0.75}}>Current colour: <span style={{display: 'inline-block', width: 14, height: 14, borderRadius: 4, background: accent, verticalAlign: 'middle', border: '1px solid var(--color-border)'}} /> used for buttons and highlights.</p>

              <label style={{display: 'block', marginTop: 16, fontSize: 14}}>Timezone
                <select value={timezone} onChange={(event) => setTimezone(event.target.value)}
                  style={{display: 'block', width: '100%', marginTop: 6, padding: '10px 12px', borderRadius: 8, border: '1px solid var(--color-border)', background: 'transparent', fontSize: 14}}>
                  {TIMEZONES.some(([value]) => value === timezone) ? null : <option value={timezone}>{timezone}</option>}
                  {TIMEZONES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </label>

              <div style={{marginTop: 16}}>
                <FileInput label="Replace the logo" value={logo} onChange={(v) => { setLogo((v as File) || null); if (v) setLogoData(null); }} accept="image/*" />
              </div>

              {suggestion.notes.length ? (
                <ul style={{marginTop: 16, paddingLeft: 18, fontSize: 14}}>
                  {suggestion.notes.map((note, index) => <li key={index} style={{marginBottom: 4}}>{note}</li>)}
                </ul>
              ) : null}

              <div style={{display: 'flex', gap: 8, marginTop: 20}}>
                <Button label={busy ? 'Saving…' : 'Looks right'} variant="primary" onClick={saveEverything} />
                <Button label="Check a different website" variant="ghost" onClick={() => { setSuggestion(null); setLogoData(null); }} />
              </div>
            </div>
          ) : (
            <div style={{marginTop: 24}}>
              <p>We have not read your site yet. Press "Check my website" above, or enter your details yourself.</p>
              <TextInput label="Business name" value={name} onChange={setName} />
              <Button label={busy ? 'Saving…' : 'Save and continue'} variant="secondary" onClick={saveEverything} />
            </div>
          )}
        </Card>
      ) : null}

      {step === 3 ? (
        <Card>
          <Heading level={2}>Put the chat window on your site</Heading>
          {platform && platform.kind !== 'other' ? (
            <p>We recognised your site as <strong>{platform.kind === 'wordpress' ? 'WordPress' : platform.kind.charAt(0).toUpperCase() + platform.kind.slice(1)}</strong>{platform.elementor ? ' with Elementor' : ''}. {handOff ? 'Your web person can add this in a minute.' : 'Add this before the closing body tag.'}</p>
          ) : (
            <p>Add this line to your website, just before the closing <code>&lt;/body&gt;</code> tag. If you do not look after your site yourself, send it to whoever does.</p>
          )}

          <TextArea label="Website embed code" value={snippet} onChange={() => {}} rows={3} />
          <div style={{display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8}}>
            <Button label="Copy embed code" variant="secondary" onClick={() => { navigator.clipboard?.writeText(snippet); setStatus('Copied.'); notify('Embed code copied.'); }} />
            <Button label="Email this to my web person" variant="secondary" onClick={() => { location.href = 'mailto:?subject=' + encodeURIComponent('Add our chat window to our website') + '&body=' + encodeURIComponent(mailBody); }} />
            <Button label={checkingSite ? 'Checking…' : 'Check my site'} variant="secondary" onClick={checkLiveSite} />
          </div>
          {install ? (
            <p role="status" style={{marginTop: 8, fontSize: 14}}>
              {install.found ? '✓ ' : ''}{install.detail}
            </p>
          ) : null}

          {hosted ? (
            <div style={{marginTop: 20}}>
              <p style={{fontSize: 14}}>No website, or cannot edit it? Use your hosted chat page instead:</p>
              <p style={{fontSize: 14}}><a href={hosted}>{hosted}</a> <Button label="Copy link" variant="ghost" onClick={() => { navigator.clipboard?.writeText(hosted); notify('Link copied.'); }} /></p>
            </div>
          ) : null}

          <Capabilities token={token} />

          <p style={{marginTop: 16}}>Anything you have not allowed yet stays off, and you can switch it on later in the Permissions tab.</p>
          <div style={{marginTop: 16}}>
            <Button label="Open my workspace" variant="primary" onClick={onDone} />
          </div>
        </Card>
      ) : null}

      <div style={{display: 'flex', gap: 8, marginTop: 16}}>
        {step > 1 ? <Button label="Back" variant="ghost" onClick={() => setStep(step - 1)} /> : null}
      </div>
      {problem ? <ErrorNote message={problem} /> : null}
      {status ? <p role="status">{status}</p> : null}
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
  const [insights, setInsights] = useState<{insights?: Record<string, unknown>[]; counts_by_outcome?: Record<string, number>}>({});
  const [live, setLive] = useState<Record<string, unknown>[]>([]);
  const [audit, setAudit] = useState<Record<string, unknown>[]>([]);
  const [supervising, setSupervising] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const days: Array<[string, string]> = [['mon','Monday'],['tue','Tuesday'],['wed','Wednesday'],['thu','Thursday'],['fri','Friday'],['sat','Saturday'],['sun','Sunday']];

  async function load() {
    try {
      const [cal, crm, onboarding, me, missed, calls] = await Promise.all([
        api('/owner/calendar'), api('/owner/crm'), api('/owner/onboarding'), api('/owner/me'),
        api('/owner/missed-calls'), api('/owner/call-insights?limit=10')]);
      setTextback(missed as {enabled?: boolean; count_30d?: number; recoveries?: Record<string, unknown>[]});
      setInsights(calls as {insights?: Record<string, unknown>[]; counts_by_outcome?: Record<string, number>});
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
      const aud = await api('/owner/supervision?limit=10') as {sessions?: Record<string, unknown>[]};
      setAudit(aud.sessions || []);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load bookings'); }
  }
  useEffect(() => { load(); }, [token]);

  // Live calls refresh every few seconds; the console is only useful if it is current.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const data = await api('/owner/live-calls') as {calls?: Record<string, unknown>[]};
        if (alive) setLive(data.calls || []);
      } catch { /* a blip must not clear the panel */ }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(id); };
  }, [token]);

  async function takeOverLive(callSid: string) {
    try {
      const result = await api('/owner/live-calls/' + encodeURIComponent(callSid) + '/takeover', 'POST', {reason: 'live takeover from Studio'}) as {caller?: string; ended?: boolean; note?: string};
      setStatus(result.ended ? 'Concierge stopped. Ring ' + (result.caller || 'the caller') + ' back now.' : (result.note || 'Concierge stopped; ring them back now.'));
      notify('Take over: ring ' + (result.caller || 'the caller') + ' back now.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not take over that call'); }
  }

  // Listening is an audio action on the media server, not a transcript view: the owner's own
  // phone rings and is joined to the caller. The caller has already been told this may happen.
  async function superviseLive(callSid: string, mode: 'listen' | 'whisper' | 'join') {
    setSupervising(callSid);
    const said = mode === 'listen'
      ? 'Your phone is ringing — answer to listen. The caller will not hear you.'
      : mode === 'whisper'
        ? 'Your phone is ringing — answer to whisper. Only the caller hears you.'
        : 'Your phone is ringing — answer to join. Everyone on the call hears you.';
    try {
      const result = await api('/owner/live-calls/' + encodeURIComponent(callSid) + '/supervise', 'POST', {mode}) as {number?: string};
      setStatus(said + (result.number ? ' Ringing ' + result.number + '.' : ''));
      notify(said);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not join that call'); }
    setSupervising('');
  }

  async function stopSupervising(callSid: string) {
    try {
      const result = await api('/owner/live-calls/' + encodeURIComponent(callSid) + '/supervise/stop', 'POST', {}) as {stopped?: number; note?: string};
      setStatus(result.stopped ? 'Stopped listening. The call carries on without you.' : (result.note || 'Nobody was listening to that call.'));
      notify(result.stopped ? 'Stopped listening.' : 'Nobody was listening.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not stop listening'); }
  }

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

      {live.length ? (
        <Card>
          <Heading level={2}>Happening now</Heading>
          <p>Listening in rings your own phone and joins it to the call. The caller has been told a team member may listen.</p>
          {live.map((call, index) => (
            <div key={index} style={{borderBottom: '1px solid var(--color-border)', paddingBottom: 8, marginBottom: 8}}>
              <strong>{String(call.caller || 'Caller')}</strong> · {Math.round(Number(call.seconds || 0) / 60)}m {Number(call.seconds || 0) % 60}s
              {!call.caller_has_spoken ? <Badge label="has not spoken" variant="warning" /> : null}
              <div style={{margin: '6px 0'}}>
                {(Array.isArray(call.transcript) ? call.transcript as Array<Record<string, string>> : []).slice(-6).map((turn, i) => (
                  <p key={i} style={{margin: '2px 0'}}><em>{turn.who}:</em> {turn.text}</p>
                ))}
              </div>
              <Button label="Take over — ring them back" variant="primary" onClick={() => takeOverLive(String(call.call_sid))} />
              {(() => {
                const control = (call.media_control || {}) as Record<string, boolean>;
                if (!control.listen) return null;
                const listening = (Array.isArray(call.supervision) ? call.supervision : []) as Array<Record<string, unknown>>;
                if (listening.length) {
                  return (
                    <p style={{margin: '8px 0 0'}}>
                      <Badge label={'Listening: ' + listening.map((leg) => String(leg.mode_label || leg.mode || '')).join(', ')} variant="success" />
                      {' '}<Button label="Stop listening" variant="secondary" onClick={() => stopSupervising(String(call.call_sid))} />
                    </p>
                  );
                }
                const sid = String(call.call_sid);
                return (
                  <p style={{margin: '8px 0 0'}}>
                    <Button label={supervising === sid ? 'Ringing…' : 'Listen in'} variant="secondary" onClick={() => superviseLive(sid, 'listen')} />
                    {' '}<Button label="Whisper" variant="secondary" onClick={() => superviseLive(sid, 'whisper')} />
                    {' '}<Button label="Join" variant="secondary" onClick={() => superviseLive(sid, 'join')} />
                  </p>
                );
              })()}
            </div>
          ))}
        </Card>
      ) : null}

      <Card>
        <Heading level={2}>Who listened</Heading>
        <p>Every time someone listens to a live call it is recorded here — who, which call, and for how long.</p>
        {audit.length ? audit.map((session, index) => {
          const seconds = Number(session.seconds || 0);
          const when = String(session.started_at || '').slice(0, 16).replace('T', ' ');
          return (
            <p key={index} style={{borderBottom: '1px solid var(--color-border)', paddingBottom: 6}}>
              <strong>{String(session.supervisor || 'Owner')}</strong> · {String(session.mode_label || session.mode || '')} · {String(session.caller || session.call_sid || 'call')} · {when}
              {' '}<Badge label={session.open ? 'listening now' : seconds ? Math.floor(seconds / 60) + 'm ' + (seconds % 60) + 's' : 'did not connect'} variant={session.open ? 'success' : seconds ? 'neutral' : 'warning'} />
              {!session.open && session.ended_reason ? <><br /><em>{String(session.ended_reason)}</em></> : null}
            </p>
          );
        }) : <p>Nobody has listened to a call yet. When someone does, it appears here.</p>}
      </Card>

      <Card>
        <Heading level={2}>Recent calls</Heading>
        <p>What happened on each call, in your own words — no transcripts to read.</p>
        {(insights.insights || []).length ? (insights.insights || []).map((call, index) => (
          <p key={index} style={{borderBottom: '1px solid var(--color-border)', paddingBottom: 6}}>
            <Badge label={String(call.outcome || '')} variant={call.outcome === 'booked' ? 'success' : call.outcome === 'unresolved' ? 'warning' : 'neutral'} />
            {' '}<strong>{String(call.from_number || 'Caller')}</strong> · {String(call.started_at || call.created_at || '').slice(0, 16)}
            <br />{String(call.summary || '')}
            {call.next_step ? <><br /><em>Next: {String(call.next_step)}</em></> : null}
          </p>
        )) : <p>No calls analysed yet. Every call your line answers will appear here.</p>}
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
  const [money30, setMoney30] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState('');

  useEffect(() => {
    Promise.all([api('/owner/crm'), api('/owner/crm/quotations'), api('/owner/social/posts'), api('/owner/media/assets'), api('/owner/revenue?days=30')])
      .then(([crm, q, p, a, rev]) => {
        setLeads(((crm as {leads?: Lead[]}).leads || []));
        setQuotes(q as Quote[]); setPosts(p as Post[]); setAssets(a as Asset[]);
        setMoney30(rev as Record<string, unknown>);
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
      {money30 ? (
        <>
          <Heading level={2}>What it earned — last 30 days</Heading>
          <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))'}}>
            <Card><strong style={{fontSize: 28}}>{String(money30.enquiries ?? 0)}</strong>
              <p>Enquiries {money30.enquiries_change_percent === null ? '' : `(${Number(money30.enquiries_change_percent) > 0 ? '+' : ''}${money30.enquiries_change_percent}% vs previous)`}</p></Card>
            <Card><strong style={{fontSize: 28}}>{money(Number(money30.accepted_cents || 0), String(money30.currency || 'NZD'))}</strong>
              <p>Accepted value {money30.accepted_change_percent === null ? '' : `(${Number(money30.accepted_change_percent) > 0 ? '+' : ''}${money30.accepted_change_percent}% vs previous)`}</p></Card>
            <Card><strong style={{fontSize: 28}}>{String(money30.accept_rate_percent ?? 0)}%</strong>
              <p>Accepted of {String(money30.quotes_sent ?? 0)} quotes sent</p></Card>
            <Card><strong style={{fontSize: 28}}>{money(Number(money30.paid_cents || 0), String(money30.currency || 'NZD'))}</strong>
              <p>Confirmed paid · {money(Number(money30.outstanding_cents || 0), String(money30.currency || 'NZD'))} outstanding</p></Card>
          </div>
          <p>
            {(Object.entries((money30.by_channel || {}) as Record<string, {enquiries: number}>)).map(([channel, value]) => (
              <span key={channel} style={{marginRight: 16}}>{channel}: <strong>{value.enquiries}</strong></span>
            ))}
          </p>
          <p role="note"><em>{String(money30.note || '')}</em></p>
        </>
      ) : null}
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
        {error ? <ErrorNote message={error} /> : null}
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
      {error ? <ErrorNote message={error} /> : null}
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
  const [token, setTokenState] = useState(() => localStorage.getItem('concierge.token') || '');
  function setToken(value: string) {
    setTokenState(value);
    if (value) localStorage.setItem('concierge.token', value);
    else localStorage.removeItem('concierge.token');
  }
  // Someone arriving from an invitation has no business details yet: start them on Setup.
  const [tab, setTab] = useState(() => {
    const newcomer = sessionStorage.getItem('concierge.startAtSetup') === '1';
    sessionStorage.removeItem('concierge.startAtSetup');
    return newcomer ? 'setup' : 'home';
  });
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

  // A rejected session drops back to sign-in instead of leaving the page in an error state.
  useEffect(() => {
    const handler = () => setToken('');
    window.addEventListener('concierge:sign-out', handler);
    return () => window.removeEventListener('concierge:sign-out', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!token) return;
    api('/owner/media/brand').then((b) => setBrand({name: b.name || '', accent: b.accent || '#c8f560', contact: b.contact || '', logo: b.logo_data || null})).catch(() => undefined);
  }, [token]);

  if (!token) {
    return (
      <Theme theme={theme}>
        <InternationalizationProvider locale={locale} messages={{...CATALOGS, [locale]: catalog}}>
          {location.hash.startsWith('#invite=') ? <Invite onToken={setToken} /> : <Login locale={locale} setLocale={setLocale} tr={tr} />}
        </InternationalizationProvider>
      </Theme>
    );
  }

  const content = (
    <>
      <TranslationNote locale={locale} />
      {tab === 'home' ? <Suspense fallback={<p style={{padding: 24}}>Loading dashboard…</p>}><Home token={token} brand={brand} /></Suspense> : tab === 'setup' ? <Setup token={token} brand={brand} setBrand={setBrand} onDone={() => setTab('home')} /> : tab === 'designs' ? <Suspense fallback={<p style={{padding: 24}}>Loading designs…</p>}><Designs token={token} /></Suspense> : tab === 'products' ? <Suspense fallback={<p style={{padding: 24}}>Loading products…</p>}><ProductsPage token={token} /></Suspense> : tab === 'bookings' ? <Bookings token={token} /> : tab === 'reports' ? <Reports token={token} /> : tab === 'quotes' ? <Suspense fallback={<p style={{padding: 24}}>Loading quotes…</p>}><Quotes token={token} brand={brand} /></Suspense> : tab === 'crm' ? <Suspense fallback={<p style={{padding: 24}}>Loading enquiries…</p>}><Crm token={token} /></Suspense> : tab === 'contacts' ? <Suspense fallback={<p style={{padding: 24}}>Loading contacts…</p>}><Contacts token={token} /></Suspense> : tab === 'permissions' ? <Suspense fallback={<p style={{padding: 24}}>Loading permissions…</p>}><PermissionsPage token={token} /></Suspense> : tab === 'social' ? <Suspense fallback={<p style={{padding: 24}}>Loading social…</p>}><Social token={token} brand={brand} /></Suspense> : <Suspense fallback={<p style={{padding: 24}}>Loading media…</p>}><Media token={token} brand={brand} setBrand={setBrand} /></Suspense>}
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
