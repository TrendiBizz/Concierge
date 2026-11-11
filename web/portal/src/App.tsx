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

type Asset = {id: string; kind: string; template: string; prompt: string; format: string; created_at: string};

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(new Error('Could not read ' + file.name));
      reader.readAsDataURL(file);
      return;
    }
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

function Studio() {
  const [token, setToken] = useState('');
  const [slug, setSlug] = useState('pukeko-construction');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const [brand, setBrand] = useState({name: '', accent: '#c8f560', contact: ''});
  const [template] = useState('showcase');
  const [headline, setHeadline] = useState('');
  const [subline, setSubline] = useState('');
  const [photos, setPhotos] = useState<File[]>([]);
  const [videoPhotos, setVideoPhotos] = useState<File[]>([]);
  const [music, setMusic] = useState<File | null>(null);
  const [videoHeadline, setVideoHeadline] = useState('');
  const [prompt, setPrompt] = useState('');
  const [assets, setAssets] = useState<Asset[]>([]);
  const [busy, setBusy] = useState(false);

  async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {'Accept': 'application/json', ...(body !== undefined ? {'Content-Type': 'application/json'} : {}), ...(token ? {Authorization: 'Bearer ' + token} : {})},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Request failed (' + response.status + ')');
    return data;
  }

  async function login() {
    setError('');
    try {
      const data = await api('/owner/auth/login', 'POST', {slug, email, password});
      setToken(data.access_token);
    } catch (e) { setError(e instanceof Error ? e.message : 'Login failed'); }
  }

  async function load() {
    try {
      const b = await api('/owner/media/brand');
      setBrand({name: b.name || '', accent: b.accent || '#c8f560', contact: b.contact || ''});
      setAssets(await api('/owner/media/assets'));
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not load media'); }
  }

  useEffect(() => { if (token) load(); }, [token]);

  async function generate(kind: 'image' | 'video' | 'ai') {
    setBusy(true); setStatus('');
    try {
      const payload: Record<string, unknown> = {};
      if (kind === 'image') {
        payload.template = template; payload.format = 'square';
        payload.headline = headline; payload.subline = subline;
        payload.photos = await Promise.all(photos.slice(0, 20).map(readFile));
      } else if (kind === 'video') {
        payload.format = 'portrait'; payload.headline = videoHeadline;
        payload.photos = await Promise.all(videoPhotos.slice(0, 20).map(readFile));
        if (music) payload.music = await readFile(music);
      } else {
        payload.prompt = prompt;
      }
      const asset = await api('/owner/media/' + (kind === 'ai' ? 'ai-image' : kind), 'POST', payload) as Asset;
      try {
        await fetch('/owner/media/assets/' + asset.id + '/to-social', {method: 'POST', headers: {Authorization: 'Bearer ' + token}});
      } catch { /* social handoff is best-effort */ }
      setStatus('Ready — added to your social composer.');
      await load();
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

  if (!token) {
    return (
      <div style={{maxWidth: 420, margin: '10vh auto', padding: 24}}>
        <Heading level={1}>Concierge Studio</Heading>
        <p>Sign in to generate branded images, videos and AI media.</p>
        <TextInput label="Business ID" value={slug} onChange={setSlug} />
        <TextInput label="Email" type="email" value={email} onChange={setEmail} />
        <TextInput label="Password" type="password" value={password} onChange={setPassword} />
        <div style={{marginTop: 16}}><Button label="Sign in" variant="primary" onClick={login} /></div>
        {error ? <p role="alert">{error}</p> : null}
      </div>
    );
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: 24}}>
      <Heading level={1}>Concierge Studio</Heading>
      <p>Branded images, short videos and AI images. Everything you generate is added to your social composer.</p>
      <div style={{display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))'}}>
        <Card>
          <Heading level={2}>Brand kit</Heading>
          <TextInput label="Brand name" value={brand.name} onChange={(v) => setBrand({...brand, name: v})} />
          <TextInput label="Contact line" value={brand.contact} onChange={(v) => setBrand({...brand, contact: v})} />
          <TextInput label="Accent colour" value={brand.accent} onChange={(v) => setBrand({...brand, accent: v})} />
          <Button label="Save brand kit" variant="secondary" onClick={async () => {
            try { await api('/owner/media/brand', 'PUT', brand); setStatus('Brand kit saved.'); } catch (e) { setStatus(e instanceof Error ? e.message : 'Save failed'); }
          }} />
        </Card>
        <Card>
          <Heading level={2}>Branded image</Heading>
          <TextInput label="Headline" value={headline} onChange={setHeadline} />
          <TextArea label="Subline or bullets" value={subline} onChange={setSubline} rows={3} />
          <FileInput label="Photos" value={photos} onChange={(v) => setPhotos(v as File[] || [])} isMultiple accept="image/*" />
          <Button label={busy ? 'Working…' : 'Generate image'} variant="primary" onClick={() => generate('image')} />
        </Card>
        <Card>
          <Heading level={2}>Short video</Heading>
          <TextInput label="Headline" value={videoHeadline} onChange={setVideoHeadline} />
          <FileInput label="Photos" value={videoPhotos} onChange={(v) => setVideoPhotos(v as File[] || [])} isMultiple accept="image/*" />
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

export default function App() {
  return <Theme theme={neutralTheme}><Studio /></Theme>;
}
