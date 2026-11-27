import {useEffect, useState} from 'react';
import type {ReactNode} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {FileInput} from '@astryxdesign/core/FileInput';
import {Badge} from '@astryxdesign/core/Badge';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {createApi} from './api';
import {StatusLine} from './StatusLine';
import {copyText} from './clipboard';

type Brand = {name: string; accent: string; contact: string; logo?: string | null};
type Suggestion = {
  website: string; name: string; accent: string; timezone?: string;
  contact?: {email?: string; phone?: string; line?: string};
  logo?: {data?: string; source?: string} | null;
  logo_alternatives?: Array<{data?: string; note?: string}>;
  platform?: {kind: string; elementor?: boolean};
  notes: string[];
};
type AutoChecks = {
  identity: boolean;
  knowledge_docs: number;
  alerts_configured: boolean;
  booking_enabled: boolean;
  calendar_connected: boolean;
  phone_configured: boolean;
  email_configured: boolean;
  sms_configured: boolean;
  integrations_connected: number;
  paused: boolean;
};

const STAGES: Array<{num: number; key: string; label: string; short: string; mins: string}> = [
  {num: 1, key: 'identity', label: '1. Business & Knowledge', short: 'Identity & Knowledge', mins: '5 min'},
  {num: 2, key: 'alerts', label: '2. Alerts & Control', short: 'Alerts & Takeover', mins: '3 min'},
  {num: 3, key: 'widget', label: '3. Website Chat & Voice', short: 'Chat Widget', mins: '5 min'},
  {num: 4, key: 'bookings', label: '4. Bookings & Calendar', short: 'Bookings & Calendar', mins: '5 min'},
  {num: 5, key: 'phone', label: '5. Phone & Voicemail', short: 'Phone & Voicemail', mins: '5 min'},
  {num: 6, key: 'channels', label: '6. Email, SMS & Tools', short: 'Email & Integrations', mins: '5 min'},
  {num: 7, key: 'launch', label: '7. Go-Live Scorecard', short: 'Review & Launch', mins: '3 min'},
];

const ACCENT_PRESETS = ['#7142d6', '#c8f560', '#2563eb', '#0d9488', '#e11d48', '#d97706'];
const TIMEZONES: Array<[string, string]> = [
  ['America/New_York', 'US Eastern (New York)'],
  ['America/Chicago', 'US Central (Austin / Chicago)'],
  ['America/Denver', 'US Mountain (Denver)'],
  ['America/Los_Angeles', 'US Pacific (Los Angeles)'],
  ['Europe/London', 'United Kingdom (London)'],
  ['Europe/Dublin', 'Ireland (Dublin)'],
  ['Europe/Berlin', 'Central Europe (Berlin)'],
  ['Australia/Sydney', 'Australia Eastern (Sydney)'],
  ['Australia/Melbourne', 'Australia Eastern (Melbourne)'],
  ['Australia/Brisbane', 'Australia (Brisbane)'],
  ['Australia/Perth', 'Australia Western (Perth)'],
  ['Pacific/Auckland', 'New Zealand (Auckland)'],
];

const PLATFORM_GUIDES: Record<string, string[]> = {
  wordpress: [
    'In WordPress Admin, open Appearance → Theme File Editor (or your Header/Footer plugin such as WPCode).',
    'Paste the one-line Concierge script just before the closing </body> tag.',
    'Save changes and clear any page cache, then click "Verify widget on my site" below.',
  ],
  shopify: [
    'In Shopify Admin, go to Online Store → Themes → Edit code.',
    'Open layout/theme.liquid and paste the Concierge script right before </body>.',
    'Click Save, then run "Verify widget on my site" below.',
  ],
  squarespace: [
    'In Squarespace, go to Website → Pages → Website Tools → Code Injection.',
    'Paste the Concierge script into the Footer box and click Save.',
    'Click "Verify widget on my site" below to confirm it is live.',
  ],
  wix: [
    'In Wix Dashboard, open Settings → Custom Code (under Development & Integrations).',
    'Click + Add Custom Code, paste the Concierge script, set to All Pages / Body - end, and Apply.',
    'Publish your site, then click "Verify widget on my site" below.',
  ],
  webflow: [
    'In Webflow, open Site Settings → Custom Code → Footer Code.',
    'Paste the Concierge script, save changes, and Publish to your custom domain.',
    'Click "Verify widget on my site" below to confirm.',
  ],
  other: [
    'Open your site HTML template or tag manager (Google Tag Manager works too).',
    'Paste the one-line Concierge script before </body> on every page where you want chat.',
    'Publish, then click "Verify widget on my site" below.',
  ],
};

function readRaw(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Could not read file'));
    reader.readAsDataURL(file);
  });
}

export function OnboardingHub({
  token,
  brand,
  setBrand,
  onNavigate,
  onDone,
  phoneStep,
}: {
  token: string;
  brand: Brand;
  setBrand: (b: Brand) => void;
  onNavigate: (tab: string) => void;
  onDone: () => void;
  phoneStep: ReactNode;
}) {
  const api = createApi(token);
  const [stage, setStage] = useState(1);
  const [completed, setCompleted] = useState<string[]>([]);
  const [launchedAt, setLaunchedAt] = useState<string | null>(null);
  const [checks, setChecks] = useState<AutoChecks>({
    identity: false, knowledge_docs: 0, alerts_configured: false, booking_enabled: false,
    calendar_connected: false, phone_configured: false, email_configured: false,
    sms_configured: false, integrations_connected: 0, paused: false,
  });

  // Business profile state
  const [website, setWebsite] = useState('');
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [accent, setAccent] = useState(brand.accent || '#7142d6');
  const [timezone, setTimezone] = useState('America/Chicago');
  const [notifyEmail, setNotifyEmail] = useState('');
  const [notifyPhone, setNotifyPhone] = useState('');
  const [publicKey, setPublicKey] = useState('');
  const [slug, setSlug] = useState('');
  const [logoData, setLogoData] = useState<string | null>(null);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);

  // Stage 1: Knowledge + Sandbox Chat
  const [noteTitle, setNoteTitle] = useState('');
  const [noteBody, setNoteBody] = useState('');
  const [sandboxQ, setSandboxQ] = useState('');
  const [sandboxLog, setSandboxLog] = useState<Array<{q: string; a: string}>>([]);

  // Stage 2: Alerts
  const [teamWebhook, setTeamWebhook] = useState('');

  // Stage 3: Widget install
  const [platformTab, setPlatformTab] = useState('wordpress');
  const [installCheck, setInstallCheck] = useState<{found: boolean; detail: string} | null>(null);
  const [helpSent, setHelpSent] = useState(false);

  // Stage 4: Slot preview
  const [previewSlots, setPreviewSlots] = useState<Array<{start?: string; label?: string}>>([]);
  const [slotsLoaded, setSlotsLoaded] = useState(false);

  // Stage 6: Inbound email readiness
  const [emailReadiness, setEmailReadiness] = useState<Record<string, unknown> | null>(null);

  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [ob, prog, hook] = await Promise.all([
        api('/owner/onboarding') as Promise<{business?: Record<string, unknown>}>,
        api('/owner/onboarding/progress') as Promise<{completed_steps: string[]; current_stage: number; launched_at: string | null; auto_checks: AutoChecks}>,
        api('/owner/team-chat-webhook').catch(() => ({url: ''})) as Promise<{url?: string}>,
      ]);
      const b = ob.business || {};
      setName(String(b.name || ''));
      setWebsite(String(b.site_url || ''));
      setTimezone(String(b.timezone || 'America/Chicago'));
      setNotifyEmail(String(b.notify_email || ''));
      setNotifyPhone(String(b.notify_phone || ''));
      setPublicKey(String(b.public_key || ''));
      setSlug(String(b.slug || ''));
      setAccent(brand.accent || '#7142d6');
      setContact(brand.contact || '');
      setTeamWebhook(hook.url || '');
      setCompleted(prog.completed_steps || []);
      setStage(prog.current_stage || 1);
      setLaunchedAt(prog.launched_at || null);
      if (prog.auto_checks) setChecks(prog.auto_checks);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load onboarding hub');
    }
  }

  useEffect(() => { void refresh(); }, [token]);

  async function saveProgress(nextStage: number, addKey?: string, launch?: boolean): Promise<boolean> {
    const prevCompleted = completed;
    const nextSteps = addKey ? Array.from(new Set([...completed, addKey])) : completed;
    setCompleted(nextSteps);
    setStage(nextStage);
    try {
      const res = await api('/owner/onboarding/progress', 'PUT', {
        completed_steps: nextSteps,
        current_stage: nextStage,
        ...(launch !== undefined ? {launched: launch} : {}),
      }) as {completed_steps: string[]; current_stage: number; launched_at: string | null};
      setCompleted(res.completed_steps || nextSteps);
      setLaunchedAt(res.launched_at || launchedAt);
      return true;
    } catch (e) {
      if (launch) {
        // Launch is refused until the server confirms the basics: say why, and do not show "Launched".
        setCompleted(prevCompleted);
        setStatus(e instanceof Error ? e.message : 'Could not launch yet.');
        return false;
      }
      return true; // saving a bookmark is non-blocking
    }
  }

  function isStageDone(key: string): boolean {
    if (completed.includes(key)) return true;
    if (key === 'identity') return checks.identity && checks.knowledge_docs > 0;
    if (key === 'alerts') return checks.alerts_configured;
    if (key === 'bookings') return checks.booking_enabled || checks.calendar_connected;
    if (key === 'phone') return checks.phone_configured;
    if (key === 'channels') return checks.email_configured || checks.integrations_connected > 0;
    if (key === 'launch') return Boolean(launchedAt);
    return false;
  }

  const doneCount = STAGES.filter((s) => isStageDone(s.key)).length;
  const pct = Math.round((doneCount / STAGES.length) * 100);
  const snippet = publicKey ? `<script src="https://chat.trendibizz.com/widget.js" data-key="${publicKey}" defer></script>` : '';

  // Stage 1 actions
  async function scanWebsite() {
    if (!website.trim()) { setStatus('Enter your website address first.'); return; }
    setBusy(true); setStatus('Reading your public pages…');
    try {
      const found = await api('/owner/onboarding/brand-suggestion?website=' + encodeURIComponent(website.trim())) as Suggestion;
      setSuggestion(found);
      if (found.name) setName(found.name);
      if (found.accent) setAccent(found.accent);
      if (found.contact?.line) setContact(found.contact.line);
      if (found.contact?.email && !notifyEmail) setNotifyEmail(found.contact.email);
      if (found.contact?.phone && !notifyPhone) setNotifyPhone(found.contact.phone);
      if (found.timezone) setTimezone(found.timezone);
      if (found.logo?.data) setLogoData(found.logo.data);
      if (found.platform?.kind && PLATFORM_GUIDES[found.platform.kind]) setPlatformTab(found.platform.kind);
      setStatus('Website scanned — review the details below and click Save.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not scan website'); }
    setBusy(false);
  }

  async function saveIdentity() {
    if (!name.trim()) { setStatus('Enter your business name.'); return; }
    setBusy(true); setStatus('Saving business identity…');
    try {
      await api('/owner/onboarding/profile', 'PATCH', {
        name: name.trim(),
        site_url: website.trim() || null,
        timezone,
        ...(notifyEmail.trim() ? {notify_email: notifyEmail.trim()} : {}),
        ...(notifyPhone.trim() ? {notify_phone: notifyPhone.trim()} : {}),
      });
      const finalLogo = logoData || (logoFile ? await readRaw(logoFile) : null);
      const saved = await api('/owner/media/brand', 'PUT', {
        name: name.trim(), accent, contact: contact.trim(),
        ...(finalLogo ? {logo: finalLogo} : {}),
      }) as {name?: string; accent?: string; contact?: string; logo_data?: string | null};
      setBrand({name: saved.name || name.trim(), accent: saved.accent || accent, contact: saved.contact || contact, logo: saved.logo_data || finalLogo});
      setStatus('Business identity saved.');
      await refresh();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save identity'); }
    setBusy(false);
  }

  async function crawlSiteKnowledge() {
    setBusy(true); setStatus('Importing your public website pages into Concierge knowledge…');
    try {
      const res = await api('/owner/knowledge/import-website', 'POST', {}) as {pages?: number; chunks?: number};
      setStatus(`Imported ${res.pages || 0} pages (${res.chunks || 0} knowledge sections). Try asking a question below!`);
      await refresh();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Website import failed'); }
    setBusy(false);
  }

  async function addQuickNote() {
    if (!noteTitle.trim() || !noteBody.trim()) { setStatus('Enter both a title and details for your knowledge note.'); return; }
    setBusy(true); setStatus('Saving knowledge note…');
    try {
      await api('/owner/knowledge', 'POST', {title: noteTitle.trim(), content: noteBody.trim(), kind: 'policy'});
      setNoteTitle(''); setNoteBody('');
      setStatus('Saved to Concierge knowledge. Test it in the sandbox below.');
      await refresh();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save note'); }
    setBusy(false);
  }

  async function runSandboxChat() {
    if (!sandboxQ.trim()) return;
    const q = sandboxQ.trim();
    setBusy(true); setSandboxQ(''); setStatus('');
    try {
      const res = await api('/owner/onboarding/test-chat', 'POST', {message: q}) as {reply: string};
      setSandboxLog((prev) => [...prev, {q, a: res.reply || '(no reply)'}]);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Sandbox chat unavailable'); }
    setBusy(false);
  }

  // Stage 2 actions
  async function saveAlerts() {
    setBusy(true); setStatus('Saving alert settings…');
    try {
      await api('/owner/onboarding/profile', 'PATCH', {
        notify_email: notifyEmail.trim() || null,
        notify_phone: notifyPhone.trim() || null,
      });
      if (teamWebhook.trim()) {
        await api('/owner/team-chat-webhook', 'PUT', {url: teamWebhook.trim()});
      }
      setStatus('Alert settings saved.');
      await refresh();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save alerts'); }
    setBusy(false);
  }

  async function sendTestAlert() {
    setBusy(true); setStatus('Queueing test alert email…');
    try {
      const res = await api('/owner/onboarding/test-alert', 'POST', {}) as {to?: string};
      setStatus(`Test alert email queued to ${res.to || notifyEmail}. Check your inbox in a moment.`);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send test alert'); }
    setBusy(false);
  }

  // Stage 3 actions
  async function verifyWidget() {
    setBusy(true); setStatus('Checking your live website for the Concierge script…');
    try {
      const res = await api('/owner/onboarding/install-check?website=' + encodeURIComponent(website.trim())) as {found: boolean; detail: string};
      setInstallCheck(res);
      setStatus(res.found ? 'Widget verified live on your site!' : res.detail);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not check your site'); }
    setBusy(false);
  }

  async function requestWhiteGloveInstall() {
    setBusy(true); setStatus('Sending install request to Trendi…');
    try {
      await api('/owner/install-request', 'POST', {
        website: website.trim(),
        platform: platformTab,
        contact_name: name.trim() || 'Owner',
        contact_phone: notifyPhone.trim() || notifyEmail.trim(),
      });
      setHelpSent(true);
      setStatus('Request sent! Our team will install and verify the widget for you.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send install request'); }
    setBusy(false);
  }

  // Stage 4 actions
  async function loadSlotPreview() {
    setBusy(true); setStatus('');
    try {
      const res = await api('/owner/onboarding/preview-slots?days=7') as {slots?: Array<{start?: string; label?: string}>};
      setPreviewSlots(res.slots || []);
      setSlotsLoaded(true);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load available slots'); }
    setBusy(false);
  }

  // Stage 6 actions
  async function checkEmailReadiness() {
    setBusy(true); setStatus('');
    try {
      const res = await api('/owner/onboarding/inbound-readiness') as Record<string, unknown>;
      setEmailReadiness(res);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not check email readiness'); }
    setBusy(false);
  }

  return (
    <VStack gap={4}>
      {/* Persistent Progress Header */}
      <Card>
        <VStack gap={3} style={{padding: 16}}>
          <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
            <div>
              <Heading level={2}>Concierge Setup &amp; Walkthrough Hub</Heading>
              <p style={{margin: '4px 0 0', opacity: 0.8}}>
                Complete these 7 short stages at your own pace. Every stage has a live check so you know it works before going live.
              </p>
            </div>
            <HStack gap={2} style={{alignItems: 'center'}}>
              <Badge label={`${doneCount} / ${STAGES.length} complete (${pct}%)`} variant={doneCount === STAGES.length ? 'success' : 'info'} />
              {launchedAt ? <Badge label="Launched" variant="success" /> : null}
              <a href={`https://trendibizz.com/guide#stage-${stage}`} target="_blank" rel="noopener noreferrer" style={{fontSize: 13}}>
                Watch the stage {stage} video ↗
              </a>
              <a href="https://trendibizz.com/help" target="_blank" rel="noopener noreferrer" style={{fontSize: 13}}>
                Help and onboarding ↗
              </a>
            </HStack>
          </HStack>
          <div style={{height: 8, borderRadius: 999, background: 'var(--color-border)', overflow: 'hidden'}}>
            <div style={{height: '100%', width: `${pct}%`, background: 'var(--color-accent, #7142d6)', transition: 'width 0.3s ease'}} />
          </div>
          <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
            {STAGES.map((s) => {
              const done = isStageDone(s.key);
              const active = stage === s.num;
              return (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => void saveProgress(s.num)}
                  style={{
                    padding: '7px 13px',
                    borderRadius: 999,
                    cursor: 'pointer',
                    fontSize: 13,
                    fontWeight: active ? 700 : 500,
                    border: active ? '2px solid var(--color-accent, #7142d6)' : '1px solid var(--color-border)',
                    background: active ? 'var(--color-accent, #7142d6)' : 'transparent',
                    color: active ? 'var(--color-on-accent, #111)' : 'inherit',
                  }}
                >
                  {done ? '✓ ' : ''}{s.label}
                </button>
              );
            })}
          </div>
        </VStack>
      </Card>

      <StatusLine text={status} />

      {/* STAGE 1: Identity & Knowledge */}
      {stage === 1 ? (
        <Card>
          <VStack gap={3} style={{padding: 16}}>
            <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
              <Heading level={2}>Stage 1 — Business Identity &amp; Knowledge</Heading>
              <Badge label={`${checks.knowledge_docs} knowledge docs loaded`} variant={checks.knowledge_docs > 0 ? 'success' : 'warning'} />
            </HStack>
            <p style={{margin: 0}}>
              Concierge answers <strong>only</strong> from the website pages and business notes you approve. A built-in <strong>Price Guard</strong> stops it from ever inventing a price — if an answer is not here, it says so and offers to pass the question to you.
            </p>
            <HStack gap={2} style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
              <div style={{flex: 1, minWidth: 240}}>
                <TextInput label="Your website URL" value={website} onChange={setWebsite} placeholder="https://yourbusiness.com" />
              </div>
              <Button label={busy ? 'Scanning…' : '1. Scan my website'} variant="secondary" isDisabled={busy} onClick={() => void scanWebsite()} />
              <Button label="2. Import site pages into Knowledge" variant="secondary" isDisabled={busy} onClick={() => void crawlSiteKnowledge()} />
            </HStack>

            <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))'}}>
              <TextInput label="Business name" value={name} onChange={setName} />
              <TextInput label="Public contact line" value={contact} onChange={setContact} placeholder="Phone or website shown on quotes" />
              <label style={{display: 'block', fontSize: 14}}>
                Country / Timezone
                <select value={timezone} onChange={(e) => setTimezone(e.target.value)}
                  style={{display: 'block', width: '100%', marginTop: 6, padding: '9px 10px', borderRadius: 8, border: '1px solid var(--color-border)', background: 'transparent'}}>
                  {TIMEZONES.some(([v]) => v === timezone) ? null : <option value={timezone}>{timezone}</option>}
                  {TIMEZONES.map(([v, lbl]) => <option key={v} value={v}>{lbl}</option>)}
                </select>
              </label>
            </div>

            <HStack gap={2} style={{alignItems: 'center', flexWrap: 'wrap'}}>
              <span style={{fontSize: 13}}>Brand colour:</span>
              {ACCENT_PRESETS.map((c) => (
                <button key={c} type="button" onClick={() => setAccent(c)} aria-label={'Colour ' + c}
                  style={{width: 28, height: 28, borderRadius: 999, background: c, border: accent === c ? '3px solid #fff' : '1px solid var(--color-border)', cursor: 'pointer'}} />
              ))}
              <FileInput label="Logo (optional)" value={logoFile} onChange={(v) => { setLogoFile((v as File) || null); if (v) setLogoData(null); }} accept="image/*" />
              <Button label="Save identity" variant="primary" isDisabled={busy} onClick={() => void saveIdentity()} />
            </HStack>

            {suggestion?.notes?.length ? (
              <ul style={{margin: 0, paddingLeft: 18, fontSize: 13, opacity: 0.85}}>
                {suggestion.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            ) : null}

            <div style={{borderTop: '1px solid var(--color-border)', paddingTop: 14}}>
              <Heading level={3}>Add a quick FAQ, Policy, or Price note (optional)</Heading>
              <VStack gap={2}>
                <TextInput label="Topic" value={noteTitle} onChange={setNoteTitle} placeholder="e.g. Call-out fee & service areas" />
                <TextArea label="Approved facts Concierge can quote" value={noteBody} onChange={setNoteBody} rows={3} placeholder="e.g. Standard site inspection is $120. We cover Austin and surrounding suburbs Mon–Fri 8am–5pm." />
                <HStack gap={2}>
                  <Button label="Save knowledge note" variant="secondary" isDisabled={busy} onClick={() => void addQuickNote()} />
                  <Button label="Manage all Knowledge →" variant="ghost" onClick={() => onNavigate('knowledge')} />
                </HStack>
              </VStack>
            </div>

            <div style={{borderTop: '1px solid var(--color-border)', paddingTop: 14}}>
              <Heading level={3}>Live Check: Test Concierge Sandbox (dry-run)</Heading>
              <p style={{margin: '0 0 8px', fontSize: 14, opacity: 0.85}}>
                Ask a real customer question below. This tests your live knowledge base without creating CRM leads or sending alerts.
              </p>
              <HStack gap={2} style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
                <div style={{flex: 1, minWidth: 240}}>
                  <TextInput label="Ask as a customer" value={sandboxQ} onChange={setSandboxQ} placeholder="e.g. What are your hours and call-out fee?" />
                </div>
                <Button label={busy ? 'Thinking…' : 'Test answer'} variant="primary" isDisabled={busy} onClick={() => void runSandboxChat()} />
              </HStack>
              {sandboxLog.map((item, i) => (
                <div key={i} style={{marginTop: 8, padding: 10, borderRadius: 8, border: '1px solid var(--color-border)'}}>
                  <p style={{margin: '0 0 4px'}}><strong>Customer:</strong> {item.q}</p>
                  <p style={{margin: 0}}><strong>Concierge:</strong> {item.a}</p>
                </div>
              ))}
            </div>

            <HStack gap={2} style={{justifyContent: 'flex-end', marginTop: 8}}>
              <Button label="Mark Stage 1 complete & continue →" variant="primary" onClick={() => void saveProgress(2, 'identity')} />
            </HStack>
          </VStack>
        </Card>
      ) : null}

      {/* STAGE 2: Alerts & Control */}
      {stage === 2 ? (
        <Card>
          <VStack gap={3} style={{padding: 16}}>
            <Heading level={2}>Stage 2 — Owner Alerts, Takeover &amp; Pause Controls</Heading>
            <p style={{margin: 0}}>
              After every enquiry, call, or voicemail, Concierge sends you <strong>one clear summary alert</strong> — never a flood of duplicates.
            </p>
            <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))'}}>
              <TextInput label="Primary alert email" value={notifyEmail} onChange={setNotifyEmail} placeholder="you@yourbusiness.com" />
              <TextInput label="Fallback alert phone (optional)" value={notifyPhone} onChange={setNotifyPhone} placeholder="+1 555 014 0140" />
              <TextInput label="Slack / Microsoft Teams webhook (optional)" value={teamWebhook} onChange={setTeamWebhook} placeholder="https://hooks.slack.com/services/..." />
            </div>
            <HStack gap={2} style={{flexWrap: 'wrap'}}>
              <Button label="Save alert channels" variant="primary" isDisabled={busy} onClick={() => void saveAlerts()} />
              <Button label="Send myself a [TEST] alert email" variant="secondary" isDisabled={busy} onClick={() => void sendTestAlert()} />
            </HStack>

            <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', marginTop: 8}}>
              <Card>
                <VStack gap={1} style={{padding: 12}}>
                  <strong>1. Per-Customer Human Takeover</strong>
                  <p style={{margin: 0, fontSize: 14}}>
                    Open <strong>Inbox</strong> or <strong>Contacts</strong> and send one reply — Concierge immediately pauses for that customer so you never talk over each other.
                  </p>
                </VStack>
              </Card>
              <Card>
                <VStack gap={1} style={{padding: 12}}>
                  <strong>2. Instant Global Pause Switch</strong>
                  <p style={{margin: 0, fontSize: 14}}>
                    Use the Pause button at the top of Studio to pause automated replies across every channel in one click while still capturing leads.
                  </p>
                </VStack>
              </Card>
            </div>

            <HStack gap={2} style={{justifyContent: 'space-between', marginTop: 8}}>
              <Button label="← Back" variant="ghost" onClick={() => void saveProgress(1)} />
              <Button label="Mark Stage 2 complete & continue →" variant="primary" onClick={() => void saveProgress(3, 'alerts')} />
            </HStack>
          </VStack>
        </Card>
      ) : null}

      {/* STAGE 3: Website Chat & Voice */}
      {stage === 3 ? (
        <Card>
          <VStack gap={3} style={{padding: 16}}>
            <Heading level={2}>Stage 3 — Website Chat &amp; Browser Voice</Heading>
            <p style={{margin: 0}}>
              One line of code adds the Concierge chat and optional browser-voice window to your site. Choose your platform below or let our team install it for you.
            </p>
            {snippet ? (
              <div style={{padding: 12, borderRadius: 8, background: 'var(--color-surface-subtle, rgba(128,128,128,0.12))', fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all'}}>
                {snippet}
              </div>
            ) : null}
            <HStack gap={2} style={{flexWrap: 'wrap'}}>
              {snippet ? <Button label="Copy 1-line script" variant="secondary" onClick={() => void copyText(snippet).then(() => setStatus('Widget script copied.'))} /> : null}
              {slug ? <a href={`https://chat.trendibizz.com/demo/${slug}`} target="_blank" rel="noopener noreferrer" style={{display: 'inline-flex', alignItems: 'center', padding: '0 8px', fontSize: 14}}>Open hosted preview ↗</a> : null}
            </HStack>

            <HStack gap={1} style={{flexWrap: 'wrap'}}>
              {Object.keys(PLATFORM_GUIDES).map((key) => (
                <Button
                  key={key}
                  label={key === 'other' ? 'Custom HTML / GTM' : key.charAt(0).toUpperCase() + key.slice(1)}
                  variant={platformTab === key ? 'primary' : 'ghost'}
                  onClick={() => setPlatformTab(key)}
                />
              ))}
            </HStack>
            <ol style={{margin: 0, paddingLeft: 20, lineHeight: 1.6}}>
              {(PLATFORM_GUIDES[platformTab] || PLATFORM_GUIDES.other).map((step, i) => <li key={i}>{step}</li>)}
            </ol>

            <HStack gap={2} style={{flexWrap: 'wrap'}}>
              <Button label={busy ? 'Checking…' : 'Verify widget on my site'} variant="primary" isDisabled={busy} onClick={() => void verifyWidget()} />
              {!helpSent ? (
                <Button label="Or: Have Trendi install it for me" variant="secondary" isDisabled={busy} onClick={() => void requestWhiteGloveInstall()} />
              ) : <Badge label="Install request sent to Trendi ✓" variant="success" />}
            </HStack>
            {installCheck ? (
              <Badge label={installCheck.found ? 'Live widget detected ✓' : installCheck.detail} variant={installCheck.found ? 'success' : 'warning'} />
            ) : null}

            <HStack gap={2} style={{justifyContent: 'space-between', marginTop: 8}}>
              <Button label="← Back" variant="ghost" onClick={() => void saveProgress(2)} />
              <Button label="Mark Stage 3 complete & continue →" variant="primary" onClick={() => void saveProgress(4, 'widget')} />
            </HStack>
          </VStack>
        </Card>
      ) : null}

      {/* STAGE 4: Bookings & Calendar */}
      {stage === 4 ? (
        <Card>
          <VStack gap={3} style={{padding: 16}}>
            <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
              <Heading level={2}>Stage 4 — Bookings &amp; Calendar Sync</Heading>
              <HStack gap={2}>
                <Badge label={checks.booking_enabled ? 'Booking ON' : 'Booking OFF'} variant={checks.booking_enabled ? 'success' : 'warning'} />
                <Badge label={checks.calendar_connected ? 'Calendar connected' : 'No calendar linked'} variant={checks.calendar_connected ? 'success' : 'neutral'} />
              </HStack>
            </HStack>
            <p style={{margin: 0}}>
              When a customer asks to book, Concierge checks your opening hours and connected calendar (Google Calendar or Microsoft 365), reads the exact time back for confirmation, then sends an instant confirmation with a self-serve reschedule/cancel link plus 24-hour and 2-hour reminders.
            </p>
            <HStack gap={2} style={{flexWrap: 'wrap'}}>
              <Button label="Configure Hours & Google Calendar →" variant="primary" onClick={() => onNavigate('bookings')} />
              <Button label="Connect Microsoft 365 Calendar →" variant="secondary" onClick={() => onNavigate('integrations')} />
              <Button label={busy ? 'Loading…' : 'Preview next 7 days’ available slots'} variant="secondary" isDisabled={busy} onClick={() => void loadSlotPreview()} />
            </HStack>
            {slotsLoaded ? (
              previewSlots.length ? (
                <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
                  {previewSlots.slice(0, 12).map((s, i) => (
                    <Badge key={i} label={s.label || s.start || 'Slot'} variant="info" />
                  ))}
                </div>
              ) : <p style={{margin: 0, opacity: 0.8}}>No open slots found in the next 7 days. Enable booking and set your opening hours in Bookings.</p>
            ) : null}

            <HStack gap={2} style={{justifyContent: 'space-between', marginTop: 8}}>
              <Button label="← Back" variant="ghost" onClick={() => void saveProgress(3)} />
              <Button label="Mark Stage 4 complete & continue →" variant="primary" onClick={() => void saveProgress(5, 'bookings')} />
            </HStack>
          </VStack>
        </Card>
      ) : null}

      {/* STAGE 5: Phone, Voicemail & Missed-Call Text-Back */}
      {stage === 5 ? (
        <VStack gap={3}>
          <Card>
            <VStack gap={2} style={{padding: 16}}>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
                <Heading level={2}>Stage 5 — Phone, Voicemail &amp; Missed-Call Text-Back</Heading>
                <Badge label={checks.phone_configured ? 'Phone line active' : 'Awaiting number'} variant={checks.phone_configured ? 'success' : 'warning'} />
              </HStack>
              <p style={{margin: 0}}>
                Trendi configures a dedicated business number tailored to your country. Callers hear a clear AI disclosure, voicemails are captured into your CRM automatically, and optional missed-call text-back texts callers who hang up early with your booking link.
              </p>
            </VStack>
          </Card>
          {phoneStep}
          <HStack gap={2} style={{justifyContent: 'space-between'}}>
            <Button label="← Back" variant="ghost" onClick={() => void saveProgress(4)} />
            <Button label="Mark Stage 5 complete & continue →" variant="primary" onClick={() => void saveProgress(6, 'phone')} />
          </HStack>
        </VStack>
      ) : null}

      {/* STAGE 6: Email, SMS & Connected Software */}
      {stage === 6 ? (
        <Card>
          <VStack gap={3} style={{padding: 16}}>
            <Heading level={2}>Stage 6 — Email, SMS &amp; Connected Software</Heading>
            <p style={{margin: 0}}>
              Wire up the rest of your office channels and connect the software you already use — Xero, Microsoft 365 Calendar, ServiceM8, Slack/Teams, Meta Messaging, or custom Webhooks (Zapier / Make).
            </p>
            <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))'}}>
              <Card>
                <VStack gap={2} style={{padding: 12}}>
                  <strong>Inbound Email</strong>
                  <Badge label={checks.email_configured ? 'Configured' : 'Optional'} variant={checks.email_configured ? 'success' : 'neutral'} />
                  <p style={{margin: 0, fontSize: 13}}>Drafts for your review (recommended) or verified auto-reply.</p>
                  <Button label="Check email readiness" variant="secondary" isDisabled={busy} onClick={() => void checkEmailReadiness()} />
                </VStack>
              </Card>
              <Card>
                <VStack gap={2} style={{padding: 12}}>
                  <strong>SMS &amp; Meta Messaging</strong>
                  <Badge label={checks.sms_configured ? 'SMS ready' : 'Optional'} variant={checks.sms_configured ? 'success' : 'neutral'} />
                  <p style={{margin: 0, fontSize: 13}}>Pair your business SMS gateway or connect WhatsApp / Messenger / IG DMs.</p>
                  <Button label="Open Permissions →" variant="secondary" onClick={() => onNavigate('permissions')} />
                </VStack>
              </Card>
              <Card>
                <VStack gap={2} style={{padding: 12}}>
                  <strong>Xero, ServiceM8 &amp; Webhooks</strong>
                  <Badge label={`${checks.integrations_connected} connected`} variant={checks.integrations_connected > 0 ? 'success' : 'neutral'} />
                  <p style={{margin: 0, fontSize: 13}}>Sync contacts to Xero, jobs to ServiceM8, or signed webhooks to Zapier/Make.</p>
                  <Button label="Open Integrations →" variant="secondary" onClick={() => onNavigate('integrations')} />
                </VStack>
              </Card>
            </div>
            {emailReadiness ? (
              <div style={{padding: 10, borderRadius: 8, border: '1px solid var(--color-border)', fontSize: 13}}>
                <strong>Email readiness:</strong> {emailReadiness.ready ? 'All links green ✓' : String(emailReadiness.summary || 'Authorize email read & send under Permissions.')}
              </div>
            ) : null}

            <HStack gap={2} style={{justifyContent: 'space-between', marginTop: 8}}>
              <Button label="← Back" variant="ghost" onClick={() => void saveProgress(5)} />
              <Button label="Mark Stage 6 complete & continue →" variant="primary" onClick={() => void saveProgress(7, 'channels')} />
            </HStack>
          </VStack>
        </Card>
      ) : null}

      {/* STAGE 7: Go-Live Scorecard & Daily Tour */}
      {stage === 7 ? (
        <Card>
          <VStack gap={3} style={{padding: 16}}>
            <Heading level={2}>Stage 7 — Go-Live Scorecard &amp; Daily Workflow</Heading>
            <p style={{margin: 0}}>
              Here is your live readiness check across the system. You can launch now and add optional channels anytime.
            </p>
            <div style={{display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))'}}>
              {[
                ['Business identity', checks.identity],
                [`Knowledge (${checks.knowledge_docs} docs)`, checks.knowledge_docs > 0],
                ['Owner alert email', checks.alerts_configured],
                ['Bookings / Calendar', checks.booking_enabled || checks.calendar_connected],
                ['Phone line', checks.phone_configured],
                ['Email / Integrations', checks.email_configured || checks.integrations_connected > 0],
              ].map(([label, ok]) => (
                <div key={String(label)} style={{padding: 10, borderRadius: 8, border: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6}}>
                  <span style={{fontSize: 14}}>{String(label)}</span>
                  <Badge label={ok ? 'Ready' : 'Optional / Pending'} variant={ok ? 'success' : 'warning'} />
                </div>
              ))}
            </div>

            <Heading level={3}>Your 4 daily screens in Studio</Heading>
            <div style={{display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))'}}>
              {[
                ['Home', 'home', 'Daily summary of enquiries, quotes, and revenue.'],
                ['Enquiries & Inbox', 'crm', 'Read conversations, score leads, or reply to take over.'],
                ['Contacts', 'contacts', 'One unified timeline per customer across all channels.'],
                ['Bookings & Quotes', 'bookings', 'Manage appointments, calendar feed, and customer quotes.'],
              ].map(([title, target, desc]) => (
                <Card key={title}>
                  <VStack gap={1} style={{padding: 12}}>
                    <strong>{title}</strong>
                    <p style={{margin: 0, fontSize: 13, opacity: 0.85}}>{desc}</p>
                    <Button label={`Open ${title}`} variant="ghost" onClick={() => onNavigate(target)} />
                  </VStack>
                </Card>
              ))}
            </div>

            <HStack gap={2} style={{justifyContent: 'space-between', marginTop: 8, flexWrap: 'wrap'}}>
              <Button label="← Back" variant="ghost" onClick={() => void saveProgress(6)} />
              <Button
                label={launchedAt ? 'Go to Home Dashboard →' : 'Launch Concierge →'}
                variant="primary"
                onClick={async () => {
                  if (await saveProgress(7, 'launch', true)) onDone();
                }}
              />
            </HStack>
          </VStack>
        </Card>
      ) : null}
    </VStack>
  );
}
