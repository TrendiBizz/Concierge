import {useEffect, useState} from 'react';
import {describeFailure} from './api';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {FileInput} from '@astryxdesign/core/FileInput';
import {Badge} from '@astryxdesign/core/Badge';
import {ProgressBar} from '@astryxdesign/core/ProgressBar';
import {DateTimeInput} from '@astryxdesign/core/DateTimeInput';

type Brand = {name: string; accent: string; contact: string; logo?: string | null};
type Asset = {id: string; kind: string; template: string; prompt: string; format: string; created_at: string};
type Account = {id: string; network: string; display_name: string; needs_reauth?: boolean};
type Post = {id: string; status: string; content: string; link?: string; hashtags?: string; last_error?: string; scheduled_at?: number | string; created_at?: string};
type Variant = {account_id: string; account_name: string; network: string; content: string; link?: string; hashtags?: string; media?: string[]; video?: string | null; limit?: number; warnings?: string[]; errors?: string[]};

function useApi(token: string) {
  return async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {method, headers: {'Accept': 'application/json', ...(body !== undefined ? {'Content-Type': 'application/json'} : {}), Authorization: 'Bearer ' + token}, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
    return data;
  };
}
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
    const image = new Image(); const url = URL.createObjectURL(file);
    image.onload = () => {
      const max = 2048; const scale = Math.min(1, max / Math.max(image.width, image.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale);
      canvas.getContext('2d')?.drawImage(image, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url); resolve(canvas.toDataURL('image/jpeg', 0.86));
    };
    image.onerror = () => { URL.revokeObjectURL(url); reject(new Error('Could not read ' + file.name)); };
    image.src = url;
  });
}

export function Media({token, brand, setBrand}: {token: string; brand: Brand; setBrand: (b: Brand) => void}) {
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
  const [usage, setUsage] = useState<{images?: {used: number; limit: number}; videos?: {used: number; limit: number}; ai?: {used: number; limit: number}; storage?: {used: number; limit: number}} | null>(null);

  useEffect(() => {
    api('/owner/media/usage').then(setUsage).catch(() => undefined);
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
      setUsage(await api('/owner/media/usage'));
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
    <div>
      <p>Branded images, short videos and AI images. Everything you generate is added to your social composer.</p>
      {usage ? (
        <div style={{display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', margin: '8px 0 16px'}}>
          <ProgressBar label="Images this month" value={usage.images?.used || 0} max={usage.images?.limit || 100} hasValueLabel />
          <ProgressBar label="Videos this month" value={usage.videos?.used || 0} max={usage.videos?.limit || 40} hasValueLabel />
          <ProgressBar label="AI images this month" value={usage.ai?.used || 0} max={usage.ai?.limit || 50} hasValueLabel />
          <ProgressBar label="Storage (MB)" value={Math.round((usage.storage?.used || 0) / 1048576)} max={Math.round((usage.storage?.limit || 0) / 1048576)} hasValueLabel />
        </div>
      ) : null}
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

export function Social({token, brand}: {token: string; brand: Brand}) {
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
  const [providers, setProviders] = useState<Record<string, boolean>>({});
  const [role, setRole] = useState('');

  async function load() {
    try {
      const [a, p, status, me] = await Promise.all([api('/owner/social/accounts'), api('/owner/social/posts'), api('/owner/social/status'), api('/owner/me')]);
      setAccounts(a as Account[]); setPosts(p as Post[]);
      setProviders(((status as {providers?: Record<string, boolean>}).providers || {}));
      setRole((me as {role: string}).role);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load social accounts'); }
  }
  useEffect(() => { load(); }, [token]);

  function oauthPath(provider: string) {
    if (provider === 'google_business') return '/owner/social/oauth/google';
    if (['facebook', 'instagram'].includes(provider)) return '/owner/social/oauth/meta/' + provider;
    return '/owner/social/oauth/' + provider;
  }

  async function connect(provider: string) {
    if (role !== 'owner') { setStatus('Only the business owner can connect accounts.'); return; }
    const popup = window.open('about:blank', 'concierge-social-oauth', 'width=620,height=760');
    if (!popup) { setStatus('Allow popups for this page to connect an account.'); return; }
    try {
      const start = await api(oauthPath(provider) + '/start', 'POST') as {authorization_url: string; state: string};
      const url = new URL(start.authorization_url);
      if (url.protocol !== 'https:' || !start.state || start.state.length < 32) throw new Error('Invalid OAuth response');
      const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('concierge-social-oauth:' + start.state) : null;
      let finished = false;
      const finish = async (data: {type?: string; state?: string; code?: string; error?: string}) => {
        if (finished || !data || data.state !== start.state) return;
        finished = true;
        channel?.close();
        try { popup.close(); } catch { /* ignore */ }
        if (data.error || !data.code) { setStatus('Authorization was cancelled or denied.'); return; }
        try {
          await api(oauthPath(provider) + '/finish', 'POST', {state: data.state, code: data.code});
          setStatus(provider.replaceAll('_', ' ') + ' connected.');
          await load();
        } catch (e) { setStatus(e instanceof Error ? e.message : 'Connection failed'); }
      };
      if (channel) channel.onmessage = (event) => { void finish(event.data); };
      window.addEventListener('message', (event) => {
        if (event.origin === location.origin && event.data?.type === 'concierge-social-oauth') void finish(event.data);
      });
      popup.location.href = url.href;
      setStatus('Continue in the provider window. Authorize the account for this business.');
    } catch (e) {
      try { popup.close(); } catch { /* ignore */ }
      setStatus(e instanceof Error ? e.message : 'Connection unavailable');
    }
  }

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

  const connectable = accounts.filter((a) => !a.needs_reauth && a.network !== 'bluesky');

  return (
    <div>
      <p>Prepare one post for each network, review the exact text, then schedule it for {brand.name || 'your business'}.</p>
      <Card>
        <Heading level={2}>Connect an account</Heading>
        <p>Choose a network and authorize it on the provider's site. You authorize only the account for this business.</p>
        <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
          {Object.entries(providers).filter(([, enabled]) => enabled).map(([provider]) => (
            <Button key={provider} label={'Connect ' + provider.replaceAll('_', ' ')} variant="secondary" onClick={() => connect(provider)} />
          ))}
        </div>
        {!Object.values(providers).some(Boolean) ? <p>Account connections are awaiting Trendi setup for this business.</p> : null}
      </Card>
      {!accounts.length ? <Card><p>No social accounts are connected yet.</p><p>Choose a network above; it appears here once connected.</p></Card> : null}
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

      <DateTimeInput label="Schedule time (optional, defaults to one hour from now)" value={(when || undefined) as never} onChange={(value) => setWhen(value || '')} description="Local time; leave blank for one hour from now." />

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
            <Badge label={post.status.replaceAll('_', ' ')} variant={post.status === 'published' ? 'success' : post.status === 'failed' ? 'error' : 'neutral'} />
            <p style={{whiteSpace: 'pre-wrap'}}>{[post.content, post.link, post.hashtags].filter(Boolean).join('\n')}</p>
            {post.last_error ? <p role="alert">{post.last_error}</p> : null}
          </Card>
        ))}
        {!posts.length ? <div className="c-empty"><strong>No drafts yet</strong><p>Nothing is published until you approve it. Ask for a post and a draft appears here first.</p></div> : null}
      </div>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


