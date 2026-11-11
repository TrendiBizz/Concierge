import {useEffect, useState} from 'react';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {FileInput} from '@astryxdesign/core/FileInput';

type Brand = {name: string; accent: string; contact: string; logo?: string | null};
type Asset = {id: string; kind: string; template: string; prompt: string; format: string; created_at: string};
type Business = {name: string; site_url: string; notify_email: string; notify_phone: string; public_key: string};
type Account = {id: string; network: string; display_name: string; needs_reauth?: boolean};
type Post = {id: string; status: string; content: string; link?: string; hashtags?: string; last_error?: string; scheduled_at?: number | string; created_at?: string};
type Variant = {account_id: string; account_name: string; network: string; content: string; link?: string; hashtags?: string; media?: string[]; video?: string | null; limit?: number; warnings?: string[]; errors?: string[]};
type Lead = {id: string; name?: string; email?: string; phone?: string; channel: string; status: string; created_at: string; message?: string};
type Turn = {role: string; content: string};
type QuoteLine = {description: string; quantity: number; unit_price_cents: number; amount_cents?: number};
type Quote = {id: string; title: string; currency: string; status: string; lines: QuoteLine[]; subtotal_cents: number; tax_cents: number; total_cents: number; notes?: string; created_at: string; lead_id: string; version: number};
type Product = {id: string; name: string; sku?: string; unit?: string; sale_price_cents: number};

function readRaw(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('Could not read ' + file.name));
    reader.readAsDataURL(file);
  });
}

async function readPhoto(file: File): Promise<string> {
  if (!file.type.startsWith('image/')) return readRaw(file);
  return new Promise((resolve, reject) => {
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      const max = 2048;
      const scale = Math.min(1, max / Math.max(image.width, image.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(image.width * scale);
      canvas.height = Math.round(image.height * scale);
      canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/jpeg', 0.86));
    };
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read ' + file.name)); };
    image.src = url;
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

function BrandHeader({brand, tab, setTab, onSignOut}: {brand: Brand; tab: string; setTab: (v: string) => void; onSignOut: () => void}) {
  return (
    <header style={{borderBottom: '1px solid var(--color-border)', padding: '16px 0', marginBottom: 24}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', maxWidth: 1040, margin: '0 auto', padding: '0 24px'}}>
        {brand.logo ? <img src={brand.logo} alt="" style={{height: 44, width: 'auto'}} /> : null}
        <div style={{display: 'flex', flexDirection: 'column'}}>
          <strong style={{fontSize: 20}}>{brand.name || 'Concierge'}</strong>
          <span style={{fontSize: 13, color: 'var(--color-text-secondary)'}}>Powered by Trendi</span>
        </div>
        <div style={{display: 'flex', gap: 8, marginLeft: 'auto'}}>
          <Button label="Setup" variant={tab === 'setup' ? 'primary' : 'ghost'} onClick={() => setTab('setup')} />
          <Button label="Bookings" variant={tab === 'bookings' ? 'primary' : 'ghost'} onClick={() => setTab('bookings')} />
          <Button label="Reports" variant={tab === 'reports' ? 'primary' : 'ghost'} onClick={() => setTab('reports')} />
          <Button label="Quotes" variant={tab === 'quotes' ? 'primary' : 'ghost'} onClick={() => setTab('quotes')} />
          <Button label="Enquiries" variant={tab === 'crm' ? 'primary' : 'ghost'} onClick={() => setTab('crm')} />
          <Button label="Social" variant={tab === 'social' ? 'primary' : 'ghost'} onClick={() => setTab('social')} />
          <Button label="Marketing media" variant={tab === 'media' ? 'primary' : 'ghost'} onClick={() => setTab('media')} />
          <Button label="Sign out" variant="ghost" onClick={onSignOut} />
        </div>
      </div>
      <div style={{height: 4, background: brand.accent || '#c8f560', marginTop: 16}} />
    </header>
  );
}

function Login({onLogin}: {onLogin: (token: string) => void}) {
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
      <Heading level={1}>Concierge</Heading>
      <p>Sign in to set up your business, generate marketing media and manage enquiries.</p>
      <TextInput label="Business ID" value={slug} onChange={setSlug} />
      <TextInput label="Email" type="email" value={email} onChange={setEmail} />
      <TextInput label="Password" type="password" value={password} onChange={setPassword} />
      <div style={{marginTop: 16}}><Button label="Sign in" variant="primary" onClick={submit} /></div>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}

function Setup({token, brand, setBrand}: {token: string; brand: Brand; setBrand: (b: Brand) => void}) {
  const api = useApi(token);
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
      setStatus('Branding saved. It now follows through to your media and portal.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Save failed'); }
    setBusy(false);
  }

  async function importSite() {
    setBusy(true); setStatus('Reading your public pages… this can take up to a minute.');
    try {
      const result = await api('/owner/knowledge/import-website', 'POST');
      setStatus('Imported ' + (result.chunks || 0) + ' knowledge chunks from ' + (result.pages || 0) + ' pages.');
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
          <Button label="Copy embed code" variant="secondary" onClick={() => { navigator.clipboard?.writeText(snippet); setStatus('Copied.'); }} />
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

function Media({token, brand, setBrand}: {token: string; brand: Brand; setBrand: (b: Brand) => void}) {
  const api = useApi(token);
  const [template] = useState('showcase');
  const [headline, setHeadline] = useState('');
  const [subline, setSubline] = useState('');
  const [photos, setPhotos] = useState<File[]>([]);
  const [videoPhotos, setVideoPhotos] = useState<File[]>([]);
  const [music, setMusic] = useState<File | null>(null);
  const [videoHeadline, setVideoHeadline] = useState('');
  const [prompt, setPrompt] = useState('');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api('/owner/media/assets').then(setAssets).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load media'));
  }, [token]);

  async function generate(kind: 'image' | 'video' | 'ai') {
    setBusy(true); setStatus('');
    try {
      const payload: Record<string, unknown> = {};
      if (kind === 'image') {
        payload.template = template; payload.format = 'square';
        payload.headline = headline; payload.subline = subline;
        payload.photos = await Promise.all(photos.slice(0, 20).map(readPhoto));
      } else if (kind === 'video') {
        payload.format = 'portrait'; payload.headline = videoHeadline;
        payload.photos = await Promise.all(videoPhotos.slice(0, 20).map(readPhoto));
        if (music) payload.music = await readRaw(music);
      } else {
        payload.prompt = prompt;
      }
      const asset = await api('/owner/media/' + (kind === 'ai' ? 'ai-image' : kind), 'POST', payload) as Asset;
      fetch('/owner/media/assets/' + asset.id + '/to-social', {method: 'POST', headers: {Authorization: 'Bearer ' + token}}).catch(() => undefined);
      setStatus('Ready — added to your social composer.');
      setAssets(await api('/owner/media/assets'));
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Render failed'); }
    setBusy(false);
  }

  async function openAsset(id: string) {
    const response = await fetch('/owner/media/assets/' + id + '/file', {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) { setStatus('Media not available.'); return; }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Marketing media</Heading>
      <p>Branded images, short videos and AI images. Everything you generate is added to your social composer.</p>
      <div style={{display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))'}}>
        <Card>
          <Heading level={2}>Brand kit</Heading>
          <TextInput label="Brand name" value={brand.name} onChange={(v) => setBrand({...brand, name: v})} />
          <TextInput label="Contact line" value={brand.contact} onChange={(v) => setBrand({...brand, contact: v})} />
          <TextInput label="Accent colour" value={brand.accent} onChange={(v) => setBrand({...brand, accent: v})} />
          <Button label="Save brand kit" variant="secondary" onClick={async () => {
            try { const saved = await api('/owner/media/brand', 'PUT', brand); setBrand({...brand, ...saved, logo: saved.logo_data || brand.logo}); setStatus('Brand kit saved.'); } catch (e) { setStatus(e instanceof Error ? e.message : 'Save failed'); }
          }} />
        </Card>
        <Card>
          <Heading level={2}>Branded image</Heading>
          <TextInput label="Headline" value={headline} onChange={setHeadline} />
          <TextArea label="Subline or bullets" value={subline} onChange={setSubline} rows={3} />
          <FileInput label="Photos" value={photos} onChange={(v) => setPhotos((v as File[]) || [])} isMultiple accept="image/*" />
          <Button label={busy ? 'Working…' : 'Generate image'} variant="primary" onClick={() => generate('image')} />
        </Card>
        <Card>
          <Heading level={2}>Short video</Heading>
          <TextInput label="Headline" value={videoHeadline} onChange={setVideoHeadline} />
          <FileInput label="Photos" value={videoPhotos} onChange={(v) => setVideoPhotos((v as File[]) || [])} isMultiple accept="image/*" />
          <FileInput label="Music (optional)" value={music} onChange={(v) => setMusic((v as File) || null)} accept="audio/*" />
          <Button label={busy ? 'Working…' : 'Generate video'} variant="primary" onClick={() => generate('video')} />
        </Card>
        <Card>
          <Heading level={2}>AI image</Heading>
          <TextArea label="Prompt" value={prompt} onChange={setPrompt} rows={3} />
          <Button label={busy ? 'Working…' : 'Generate AI image'} variant="primary" onClick={() => generate('ai')} />
        </Card>
      </div>
      {status ? <p role="status">{status}</p> : null}
      <Heading level={2}>Your media</Heading>
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))'}}>
        {assets.map((asset) => (
          <Card key={asset.id}>
            <strong>{asset.kind === 'video' ? 'Video' : asset.kind === 'ai' ? 'AI image' : 'Branded image'}</strong>
            <p>{asset.template} · {new Date(asset.created_at).toLocaleString()}</p>
            <Button label="Open" variant="secondary" onClick={() => openAsset(asset.id)} />
          </Card>
        ))}
      </div>
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


function Social({token, brand}: {token: string; brand: Brand}) {
  const api = useApi(token);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [content, setContent] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [link, setLink] = useState('');
  const [hashtags, setHashtags] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [when, setWhen] = useState('');
  const [month, setMonth] = useState(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), 1); });

  async function load() {
    try {
      const [a, p] = await Promise.all([api('/owner/social/accounts'), api('/owner/social/posts')]);
      setAccounts(a as Account[]); setPosts(p as Post[]);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load social accounts'); }
  }
  useEffect(() => { load(); }, [token]);

  async function upload(): Promise<string[] | undefined> {
    if (!file) return undefined;
    const response = await fetch('/owner/social/media', {method: 'POST', headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream'}, body: file});
    if (!response.ok) throw new Error('Media upload failed');
    const data = await response.json();
    return ['upload:' + data.id];
  }

  async function prepare() {
    setBusy(true); setStatus('');
    try {
      if (!selected.length) throw new Error('Choose at least one connected account');
      const media = await upload();
      const draft = {content, account_ids: selected, link, hashtags, media: media || [], options: {}};
      const result = await api('/owner/social/compose', 'POST', draft) as Variant[];
      setVariants(result);
      setStatus('Previews ready. Review each network version before scheduling.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Compose failed'); }
    setBusy(false);
  }

  async function saveVariant(variant: Variant, schedule: boolean) {
    setBusy(true); setStatus('');
    try {
      const media = variant.media || [];
      const draft = {content: variant.content, account_ids: [variant.account_id], link: variant.link || '', hashtags: variant.hashtags || '', media, video: variant.video || null, options: {}};
      const saved = await api('/owner/social/posts', 'POST', draft) as {id: string};
      if (schedule) {
        await api('/owner/social/posts/' + saved.id + '/submit', 'POST');
        const at = when ? Math.floor(new Date(when).getTime() / 1000) : Math.floor(Date.now() / 1000) + 3600;
        const approval = await api('/owner/social/posts/' + saved.id + '/approval-request', 'POST', {scheduled_at: at}) as {token: string};
        await api('/owner/social/approvals/' + approval.token + '/approve', 'POST');
        setStatus('Scheduled in Concierge. Live delivery depends on operator publishing being enabled.');
      } else {
        setStatus('Draft saved. Submit it for approval when ready.');
      }
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the post'); }
    setBusy(false);
  }

  const connectable = accounts.filter((a) => !a.needs_reauth && !['mastodon', 'bluesky'].includes(a.network));

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Social</Heading>
      <p>Prepare one post for each network, review the exact text, then schedule it for {brand.name || 'your business'}.</p>
      {!accounts.length ? <Card><p>No social accounts are connected yet.</p><p>Connect a network in the workspace first; it appears here once connected.</p></Card> : null}
      {accounts.length ? (
        <Card>
          <Heading level={2}>New post</Heading>
          <TextArea label="Post" value={content} onChange={setContent} rows={5} />
          <TextInput label="Link (optional)" type="url" value={link} onChange={setLink} />
          <TextInput label="Hashtags (optional)" value={hashtags} onChange={setHashtags} />
          <FileInput label="Image or video (optional)" value={file} onChange={(v) => setFile((v as File) || null)} accept="image/*,video/*" />
          <div style={{margin: '12px 0'}}>
            <strong>Accounts</strong>
            {connectable.map((account) => (
              <label key={account.id} style={{display: 'block', margin: '6px 0'}}>
                <input type="checkbox" checked={selected.includes(account.id)} onChange={(e) => setSelected(e.target.checked ? [...selected, account.id] : selected.filter((id) => id !== account.id))} />{' '}
                {account.network.replaceAll('_', ' ')} — {account.display_name}
              </label>
            ))}
          </div>
          <Button label={busy ? 'Preparing…' : 'Prepare previews'} variant="primary" onClick={prepare} />
        </Card>
      ) : null}

      {variants.map((variant) => (
        <Card key={variant.account_id}>
          <Heading level={2}>{variant.network.replaceAll('_', ' ')} — {variant.account_name}</Heading>
          <TextArea label="Exact post text" value={variant.content} onChange={(v) => setVariants(variants.map((item) => item.account_id === variant.account_id ? {...item, content: v} : item))} rows={5} />
          <p>{variant.limit ? variant.content.length + ' / ' + variant.limit + ' characters' : ''}</p>
          {variant.errors?.map((error) => <p key={error} role="alert">{error}</p>)}
          <Button label="Save draft" variant="secondary" onClick={() => saveVariant(variant, false)} />
          <Button label="Schedule" variant="primary" onClick={() => saveVariant(variant, true)} />
        </Card>
      ))}

      <TextInput label="Schedule time (optional, defaults to one hour from now)" type="text" value={when} onChange={setWhen} description="Format: 2026-11-12T09:00" />

      <Heading level={2}>Calendar</Heading>
      <div style={{display: 'flex', alignItems: 'center', gap: 12, margin: '8px 0'}}>
        <Button label="←" variant="ghost" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} />
        <strong>{month.toLocaleString('en-NZ', {month: 'long', year: 'numeric'})}</strong>
        <Button label="→" variant="ghost" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} />
      </div>
      {(() => {
        const start = new Date(month.getFullYear(), month.getMonth(), 1);
        const offset = (start.getDay() + 6) % 7;
        const cells = Array.from({length: 42}, (_, i) => new Date(month.getFullYear(), month.getMonth(), 1 - offset + i));
        const byDay: Record<string, Post[]> = {};
        for (const post of posts) {
          const raw = post.scheduled_at || post.created_at;
          if (!raw) continue;
          const date = typeof raw === 'number' ? new Date(raw * 1000) : new Date(raw);
          const key = date.toISOString().slice(0, 10);
          (byDay[key] = byDay[key] || []).push(post);
        }
        return (
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6}}>
            {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((day) => <div key={day} style={{fontSize: 12, color: 'var(--color-text-secondary)'}}>{day}</div>)}
            {cells.map((date) => {
              const key = date.toISOString().slice(0, 10);
              const items = byDay[key] || [];
              const inMonth = date.getMonth() === month.getMonth();
              return (
                <div key={key} style={{minHeight: 92, padding: 6, border: '1px solid var(--color-border)', borderRadius: 8, opacity: inMonth ? 1 : 0.4}}>
                  <div style={{fontSize: 12}}>{date.getDate()}</div>
                  {items.slice(0, 2).map((post) => (
                    <div key={post.id} style={{fontSize: 11, marginTop: 4, padding: 4, background: 'var(--color-background-muted)', borderRadius: 4}}>
                      {post.status.replaceAll('_', ' ')} · {post.content.slice(0, 30)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        );
      })()}

      <Heading level={2}>Your posts</Heading>
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))'}}>
        {posts.map((post) => (
          <Card key={post.id}>
            <strong>{post.status.replaceAll('_', ' ')}</strong>
            <p style={{whiteSpace: 'pre-wrap'}}>{[post.content, post.link, post.hashtags].filter(Boolean).join('\n')}</p>
            {post.last_error ? <p role="alert">{post.last_error}</p> : null}
          </Card>
        ))}
        {!posts.length ? <p>No drafts yet.</p> : null}
      </div>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


function Crm({token}: {token: string}) {
  const api = useApi(token);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [appointments, setAppointments] = useState<Record<string, unknown>[]>([]);
  const [todos, setTodos] = useState<Record<string, unknown>[]>([]);
  const [query, setQuery] = useState('');
  const [transcripts, setTranscripts] = useState<Record<string, Turn[]>>({});
  const [status, setStatus] = useState('');

  useEffect(() => {
    api('/owner/crm').then((data) => {
      setLeads((data.leads || []) as Lead[]);
      setAppointments((data.appointments || []) as Record<string, unknown>[]);
      setTodos((data.todos || []) as Record<string, unknown>[]);
    }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load enquiries'));
  }, [token]);

  async function transcript(id: string) {
    if (transcripts[id]) return;
    try {
      const turns = await api('/owner/crm/leads/' + id + '/transcript') as Turn[];
      setTranscripts({...transcripts, [id]: turns});
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Transcript unavailable'); }
  }

  const shown = leads.filter((lead) => {
    const text = [lead.name, lead.email, lead.phone, lead.message].filter(Boolean).join(' ').toLowerCase();
    return !query || text.includes(query.toLowerCase());
  });

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>CRM and enquiries</Heading>
      <p>Every enquiry from chat, email, SMS and phone lands here, with the conversation and next step.</p>
      <TextInput label="Search enquiries" value={query} onChange={setQuery} />
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))'}}>
        {shown.map((lead) => (
          <Card key={lead.id}>
            <Heading level={2}>{lead.name || lead.email || lead.phone || 'Enquiry'}</Heading>
            <p>{lead.channel} · {lead.status} · {new Date(lead.created_at).toLocaleString()}</p>
            <p>{[lead.email, lead.phone].filter(Boolean).join(' · ')}</p>
            {lead.message ? <p style={{whiteSpace: 'pre-wrap'}}>{lead.message}</p> : null}
            <Button label="Conversation" variant="secondary" onClick={() => transcript(lead.id)} />
            {transcripts[lead.id] ? (
              <div>
                {transcripts[lead.id].length ? transcripts[lead.id].map((turn, index) => (
                  <p key={index}><strong>{turn.role === 'user' ? 'Customer' : 'Concierge'}:</strong> {turn.content}</p>
                )) : <p>No saved transcript.</p>}
              </div>
            ) : null}
          </Card>
        ))}
        {!shown.length ? <p>No enquiries yet. Connected channels will capture them here.</p> : null}
      </div>
      <div style={{display: 'flex', gap: 24, marginTop: 24, flexWrap: 'wrap'}}>
        <div><Heading level={2}>Appointments</Heading>{appointments.length ? appointments.map((a, i) => <p key={i}>{String(a.title || a.name || 'Appointment')} · {String(a.start_at || a.start || '')}</p>) : <p>None booked.</p>}</div>
        <div><Heading level={2}>Tasks</Heading>{todos.length ? todos.map((t, i) => <p key={i}>{String(t.title || 'Task')} · {String(t.status || '')}</p>) : <p>No open tasks.</p>}</div>
      </div>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


function money(cents: number, currency: string) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency: currency || 'NZD'}).format((cents || 0) / 100);
}

function Quotes({token, brand}: {token: string; brand: Brand}) {
  const api = useApi(token);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [role, setRole] = useState('');
  const [leadId, setLeadId] = useState('');
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [tax, setTax] = useState(15);
  const [lines, setLines] = useState<Array<{description: string; quantity: string; price: string}>>([{description: '', quantity: '1', price: ''}]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [q, c, p, me] = await Promise.all([api('/owner/crm/quotations'), api('/owner/crm'), api('/owner/products'), api('/owner/me')]);
      setQuotes(q as Quote[]);
      setLeads(((c as {leads?: Lead[]}).leads || []) as Lead[]);
      setProducts(p as Product[]);
      setRole((me as {role: string}).role);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load quotations'); }
  }
  useEffect(() => { load(); }, [token]);

  function addProduct(id: string) {
    const product = products.find((item) => item.id === id);
    if (!product) return;
    setLines([...lines, {description: product.name, quantity: '1', price: (product.sale_price_cents / 100).toFixed(2)}]);
  }

  async function save() {
    setBusy(true); setStatus('');
    try {
      const body = {
        lead_id: leadId, title, currency: 'NZD', tax_basis_points: Math.round(tax * 100),
        lines: lines.filter((line) => line.description.trim()).map((line) => ({
          description: line.description.trim(), quantity: line.quantity, unit_price_cents: Math.round(Number(line.price) * 100),
        })),
        notes,
      };
      await api('/owner/crm/quotations', 'POST', body);
      setStatus('Quotation saved as a draft. The owner reviews and signs it off.');
      setTitle(''); setNotes(''); setLines([{description: '', quantity: '1', price: ''}]);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the quotation'); }
    setBusy(false);
  }

  async function printQuote(id: string) {
    const response = await fetch('/owner/crm/quotations/' + id + '/print', {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) { setStatus('Could not prepare the quotation.'); return; }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function signOff(id: string, version: number) {
    setBusy(true); setStatus('');
    try {
      await api('/owner/crm/quotations/' + id + '/status', 'POST', {status: 'reviewed', version});
      setStatus('Quotation reviewed and signed off.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Sign-off failed'); }
    setBusy(false);
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Quotations</Heading>
      <p>Build a quote from your enquiry and products. Prices are your sale prices. The business owner reviews and signs off before it is accepted.</p>
      <div style={{display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))'}}>
        <Card>
          <Heading level={2}>New quotation</Heading>
          <label style={{display: 'block', margin: '8px 0'}}>
            Enquiry
            <select value={leadId} onChange={(e) => setLeadId(e.target.value)} style={{display: 'block', width: '100%', padding: 8}}>
              <option value="">Choose an enquiry</option>
              {leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.name || lead.email || lead.phone || lead.id}</option>)}
            </select>
          </label>
          <TextInput label="Title" value={title} onChange={setTitle} />
          <TextInput label="Tax %" value={String(tax)} onChange={(v) => setTax(Number(v) || 0)} />
          <label style={{display: 'block', margin: '8px 0'}}>
            Add from product catalogue
            <select value="" onChange={(e) => addProduct(e.target.value)} style={{display: 'block', width: '100%', padding: 8}}>
              <option value="">Choose a product</option>
              {products.map((product) => <option key={product.id} value={product.id}>{product.name} — {money(product.sale_price_cents, 'NZD')}</option>)}
            </select>
          </label>
          {lines.map((line, index) => (
            <div key={index} style={{display: 'grid', gridTemplateColumns: '2fr 0.7fr 1fr', gap: 8, margin: '8px 0'}}>
              <input aria-label="Line description" placeholder="Description" value={line.description} onChange={(e) => setLines(lines.map((item, i) => i === index ? {...item, description: e.target.value} : item))} style={{padding: 8}} />
              <input aria-label="Quantity" placeholder="Qty" value={line.quantity} onChange={(e) => setLines(lines.map((item, i) => i === index ? {...item, quantity: e.target.value} : item))} style={{padding: 8}} />
              <input aria-label="Unit price" placeholder="Unit price" value={line.price} onChange={(e) => setLines(lines.map((item, i) => i === index ? {...item, price: e.target.value} : item))} style={{padding: 8}} />
            </div>
          ))}
          <Button label="Add line" variant="ghost" onClick={() => setLines([...lines, {description: '', quantity: '1', price: ''}])} />
          <TextArea label="Notes" value={notes} onChange={setNotes} rows={3} />
          <Button label={busy ? 'Saving…' : 'Save quotation'} variant="primary" onClick={save} />
        </Card>
        <Card>
          <Heading level={2}>How sign-off works</Heading>
          <p>Draft → reviewed (owner only) → accepted or declined.</p>
          <p>Concierge never sends a price without the owner's approval. Your branding: <strong>{brand.name || 'your business'}</strong>.</p>
        </Card>
      </div>
      <Heading level={2}>Your quotations</Heading>
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))'}}>
        {quotes.map((quote) => (
          <Card key={quote.id}>
            <Heading level={2}>{quote.title}</Heading>
            <p><strong>{quote.status}</strong> · {money(quote.total_cents, quote.currency)} incl. {money(quote.tax_cents, quote.currency)} tax</p>
            {quote.lines.map((line, index) => <p key={index}>{line.description} · {line.quantity} × {money(line.unit_price_cents, quote.currency)}</p>)}
            {quote.notes ? <p>{quote.notes}</p> : null}
            <Button label="Print / PDF" variant="secondary" onClick={() => printQuote(quote.id)} />
            {role === 'owner' && quote.status === 'draft' ? <Button label="Review and sign off" variant="primary" onClick={() => signOff(quote.id, quote.version)} /> : null}
          </Card>
        ))}
        {!quotes.length ? <p>No quotations yet.</p> : null}
      </div>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


function Bookings({token}: {token: string}) {
  const api = useApi(token);
  const [calendar, setCalendar] = useState<{configured?: boolean; connected?: boolean; provider?: string}>({});
  const [appointments, setAppointments] = useState<Record<string, unknown>[]>([]);
  const [status, setStatus] = useState('');

  useEffect(() => {
    Promise.all([api('/owner/calendar'), api('/owner/crm')]).then(([cal, crm]) => {
      setCalendar(cal as {configured?: boolean; connected?: boolean; provider?: string});
      setAppointments(((crm as {appointments?: Record<string, unknown>[]}).appointments || []));
    }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load bookings'));
  }, [token]);

  async function connect() {
    try {
      const result = await api('/owner/calendar/start', 'POST') as {authorization_url?: string};
      if (result.authorization_url) window.location.href = result.authorization_url;
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Calendar connection unavailable'); }
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Bookings</Heading>
      <p>Appointments booked by Concierge, with the enquiry and confirmation kept together.</p>
      <Card>
        <Heading level={2}>Calendar</Heading>
        <p>{calendar.connected ? 'Connected to ' + (calendar.provider || 'your calendar') + '.' : calendar.configured ? 'Calendar connection is available but not connected.' : 'Calendar connection is awaiting Trendi setup.'}</p>
        {calendar.configured && !calendar.connected ? <Button label="Connect Google Calendar" variant="primary" onClick={connect} /> : null}
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

function Shell() {
  const [token, setToken] = useState('');
  const [tab, setTab] = useState('setup');
  const [brand, setBrand] = useState<Brand>({name: '', accent: '#c8f560', contact: ''});
  const api = useApi(token);

  useEffect(() => {
    document.title = brand.name ? brand.name + ' — Concierge' : 'Concierge';
  }, [brand.name]);

  useEffect(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('/studio/sw.js').catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!token) return;
    api('/owner/media/brand').then((b) => setBrand({name: b.name || '', accent: b.accent || '#c8f560', contact: b.contact || '', logo: b.logo_data || null})).catch(() => undefined);
  }, [token]);

  if (!token && location.hash.startsWith('#invite=')) return <Invite onToken={setToken} />;
  if (!token) return <Login onLogin={setToken} />;

  const accentStyle = {
    '--color-accent': brand.accent || '#c8f560',
    '--color-on-accent': '#101408',
    '--color-background-body': '#ffffff',
  } as React.CSSProperties;

  return (
    <div style={accentStyle}>
      <BrandHeader brand={brand} tab={tab} setTab={setTab} onSignOut={() => setToken('')} />
      {tab === 'setup' ? <Setup token={token} brand={brand} setBrand={setBrand} /> : tab === 'bookings' ? <Bookings token={token} /> : tab === 'reports' ? <Reports token={token} /> : tab === 'quotes' ? <Quotes token={token} brand={brand} /> : tab === 'crm' ? <Crm token={token} /> : tab === 'social' ? <Social token={token} brand={brand} /> : <Media token={token} brand={brand} setBrand={setBrand} />}
    </div>
  );
}

export default function App() {
  return <Theme theme={neutralTheme}>{location.hash === '#admin' ? <Admin /> : <Shell />}</Theme>;
}
