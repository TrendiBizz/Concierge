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

function Shell() {
  const [token, setToken] = useState('');
  const [tab, setTab] = useState('setup');
  const [brand, setBrand] = useState<Brand>({name: '', accent: '#c8f560', contact: ''});
  const api = useApi(token);

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
      {tab === 'setup' ? <Setup token={token} brand={brand} setBrand={setBrand} /> : <Media token={token} brand={brand} setBrand={setBrand} />}
    </div>
  );
}

export default function App() {
  return <Theme theme={neutralTheme}><Shell /></Theme>;
}
