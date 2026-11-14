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
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Grid} from '@astryxdesign/core/Grid';
import {HStack} from '@astryxdesign/core/HStack';
import {VStack} from '@astryxdesign/core/VStack';
import {Text} from '@astryxdesign/core/Text';
import {Timestamp} from '@astryxdesign/core/Timestamp';
import {StatusLine} from './StatusLine';
import {MoreMenu} from '@astryxdesign/core/MoreMenu';
import {Skeleton} from '@astryxdesign/core/Skeleton';
import {useNotify} from './Notify';

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

/** The actual bytes, shown as a picture: the difference between "nothing generated" and a result. */
function AssetPreview({token, id, video}: {token: string; id: string; video: boolean}) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let url = '';
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/owner/media/assets/' + id + '/file', {headers: {Authorization: 'Bearer ' + token}});
        if (!response.ok) return;
        url = URL.createObjectURL(await response.blob());
        if (!cancelled) setSrc(url);
      } catch {
        // A missing thumbnail must never break the page.
      }
    })();
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [token, id]);
  if (!src) return <div className="c-thumb c-thumb-empty" aria-hidden="true" />;
  return video
    ? <video className="c-thumb" src={src} muted playsInline />
    : <img className="c-thumb" src={src} alt="" />;
}

export function Media({token}: {token: string}) {
  const api = useApi(token);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(true);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [status, setStatus] = useState('');
  const notify = useNotify();
  // Which action is running, so one button never claims to be another's work.
  const [busy, setBusy] = useState<'' | 'upload' | 'delete' | 'send'>('');
  const [selected, setSelected] = useState<string[]>([]);
  const [usage, setUsage] = useState<{storage?: {used: number; limit: number}; assets?: number} | null>(null);

  useEffect(() => {
    api('/owner/media/usage').then(setUsage).catch(() => undefined);
    api('/owner/media/assets').then(setAssets)
      .catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load media'))
      .finally(() => setLoading(false));
  }, [token]);

  // Bytes, not a spinner: a 180 MB video over a phone connection needs a number.
  function uploadOne(file: File): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open('POST', '/owner/media/upload');
      request.setRequestHeader('Authorization', 'Bearer ' + token);
      request.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
      request.upload.onprogress = (event) => {
        if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
      };
      request.onload = () => {
        if (request.status >= 200 && request.status < 300) { resolve(); return; }
        let detail = 'Upload failed (' + request.status + ')';
        try {
          const body = JSON.parse(request.responseText);
          if (typeof body.detail === 'string') detail = body.detail;
        } catch { /* keep the status message */ }
        reject(new Error(detail));
      };
      request.onerror = () => reject(new Error('Could not reach the server'));
      request.send(file);
    });
  }

  async function uploadFilesNow() {
    if (!uploadFiles.length) return;
    setBusy('upload');
    const total = uploadFiles.length;
    const failed: string[] = [];
    for (const [index, file] of uploadFiles.entries()) {
      setStatus(total > 1 ? 'Uploading ' + (index + 1) + ' of ' + total + '…' : 'Uploading…');
      setProgress(0);
      try { await uploadOne(file); }
      catch (e) { failed.push(file.name + ': ' + (e instanceof Error ? e.message : 'failed')); }
    }
    setProgress(null);
    setAssets(await api('/owner/media/assets'));
    setUsage(await api('/owner/media/usage'));
    const uploaded = total - failed.length;
    setUploadFiles([]);
    setBusy('');
    if (uploaded) {
      setStatus('Uploaded ' + uploaded + (uploaded === 1 ? ' file — it is' : ' files — they are')
                + ' in Your media below. Open Social to post.');
      notify('Uploaded ' + uploaded + (uploaded === 1 ? ' file' : ' files'), 'info');
    }
    if (failed.length) setStatus('Could not upload ' + failed.join('; '));
  }

  function takeFiles(picked: File[]) {
    const allowed = picked.filter((file) => /^(image|video)\//.test(file.type));
    const rejected = picked.length - allowed.length;
    if (rejected > 0) setStatus('Skipped ' + rejected + ' file' + (rejected === 1 ? '' : 's')
                                + ' — only photos and videos can be posted.');
    setUploadFiles(allowed);
  }

  async function sendToSocial(asset: Asset) {
    setBusy('send'); setStatus('Adding to your social composer…');
    try {
      await api('/owner/media/assets/' + asset.id + '/to-social', 'POST', {});
      setStatus('Added to your social composer. Open Social to write the post.');
      notify('Added to your social composer', 'info');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send that to social'); }
    setBusy('');
  }

  function toggleSelected(id: string) {
    setSelected((current) => current.includes(id)
      ? current.filter((value) => value !== id)
      : [...current, id]);
  }

  async function removeSelected() {
    if (!selected.length) return;
    if (!window.confirm('Delete ' + selected.length + ' item' + (selected.length === 1 ? '' : 's') + '? This cannot be undone.')) return;
    setBusy('delete'); setStatus('Deleting ' + selected.length + '…');
    try {
      const result = await api('/owner/media/assets/delete', 'POST', {ids: selected}) as {deleted: number};
      setSelected([]);
      setAssets(await api('/owner/media/assets'));
      setUsage(await api('/owner/media/usage'));
      setStatus('Deleted ' + (result?.deleted ?? selected.length) + '. Your storage went down.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not delete those'); }
    setBusy('');
  }

  async function removeAsset(asset: Asset) {
    const label = asset.kind === 'video' ? 'video' : 'image';
    if (!window.confirm('Delete this ' + label + '? This cannot be undone.')) return;
    setBusy('delete'); setStatus('Deleting…');
    try {
      await api('/owner/media/assets/' + asset.id, 'DELETE');
      setAssets(await api('/owner/media/assets'));
      setUsage(await api('/owner/media/usage'));
      setStatus('Deleted. Your storage went down.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not delete that'); }
    setBusy('');
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
      <Text>
        Upload the photos and videos you want posted — your own footage, or something you made with
        an AI tool elsewhere. We publish them to your social accounts. We do not generate images or
        video.
      </Text>
      {usage ? (
        <div style={{display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', margin: '8px 0 16px'}}>
          <ProgressBar label="Storage used" value={usage.storage?.used || 0}
                       max={usage.storage?.limit || 1} />
          <Text size="sm" color="secondary">
            {((usage.storage?.used || 0) / 1048576).toFixed(1)} MB of{' '}
            {Math.round((usage.storage?.limit || 0) / 1048576)} MB used
          </Text>
        </div>
      ) : null}
      <div style={{display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))'}}>
        <Card>
          <Heading level={2}>Upload your media</Heading>
          <p style={{fontSize: 13, opacity: 0.75}}>
            A photo or a video you already have — filmed yourself, from your phone, or made with an
            AI tool elsewhere. We will publish it to your social accounts. We do not make images or
            video for you; we post what you bring.
          </p>
          <div
            onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setIsDragging(false);
              takeFiles(Array.from(event.dataTransfer.files));
            }}
            style={{
              border: '2px dashed ' + (isDragging ? 'var(--color-accent, #c8f560)' : 'var(--color-border)'),
              borderRadius: 12,
              padding: 16,
              margin: '8px 0',
              textAlign: 'center',
              background: isDragging ? 'rgba(200,245,96,0.08)' : 'transparent',
            }}>
            <Text>Drop photos or videos here</Text>
            <FileInput label="…or choose files (PNG, JPEG, WebP, MP4, MOV, WebM)"
                       value={uploadFiles} isMultiple
                       onChange={(value) => takeFiles(
                         Array.isArray(value) ? value : value ? [value] : [])}
                       accept="image/*,video/*" />
          </div>
          {uploadFiles.length ? (
            <Text size="sm" color="secondary">
              {uploadFiles.length} file{uploadFiles.length === 1 ? '' : 's'} ready:{' '}
              {uploadFiles.map((file) => file.name).join(', ')}
            </Text>
          ) : null}
          {progress !== null ? (
            <ProgressBar label="Uploading" value={progress} max={100} hasValueLabel />
          ) : null}
          <Button label={busy === 'upload' ? 'Uploading…' : 'Upload for socials'} variant="primary"
                  isDisabled={busy !== '' || !uploadFiles.length}
                  onClick={() => void uploadFilesNow()} />
          <Text size="sm" color="secondary">
            Your brand name, colour and logo live in Setup — they appear on your quotes, invoices
            and chat widget.
          </Text>
        </Card>
      </div>
      {<StatusLine text={status} />}
      <Heading level={2}>Your media</Heading>
      {assets.length ? (
        <HStack gap={3} vAlign="center" style={{margin: '4px 0 10px', flexWrap: 'wrap'}}>
          <CheckboxInput label="Select all" value={selected.length > 0 && selected.length === assets.length}
                         onChange={(checked) => setSelected(checked ? assets.map((a) => a.id) : [])} />
          <Text size="sm" color="secondary">{selected.length} of {assets.length} selected</Text>
          <Button label={busy === 'delete' ? 'Deleting…' : 'Delete selected' + (selected.length ? ' (' + selected.length + ')' : '')}
                  variant="secondary" isDisabled={!selected.length || busy !== ''}
                  onClick={() => void removeSelected()} />
        </HStack>
      ) : null}
      {loading ? (
        <Grid columns={{minWidth: 220}} gap={3}>
          {[0, 1, 2].map((index) => <Skeleton key={index} height={260} radius="rounded" />)}
        </Grid>
      ) : null}
      {loading || assets.length ? null : (
        <EmptyState title="Nothing uploaded yet"
                    description="Add a photo or a video you already have, and it will appear here ready to post."
                    headingLevel={3} />
      )}
      <Grid columns={{minWidth: 220}} gap={3}>
        {assets.map((asset) => (
          <Card key={asset.id}>
            <CheckboxInput label="Select" isLabelHidden value={selected.includes(asset.id)}
                           onChange={() => toggleSelected(asset.id)} />
            <AssetPreview token={token} id={asset.id} video={asset.kind === 'video'} />
            <VStack gap={1} hAlign="start">
              <Badge label={asset.kind === 'video' ? 'Video' : 'Image'} />
              <Timestamp value={asset.created_at} format="date_time" type="supporting" />
            </VStack>

            <HStack gap={2} vAlign="center">
              <Button label="Open" variant="secondary" onClick={() => openAsset(asset.id)} />
              <MoreMenu label="More actions for this media" items={[
                {label: 'Open full size', onClick: () => openAsset(asset.id)},
                {label: 'Send to social', onClick: () => void sendToSocial(asset)},
                {label: busy === 'delete' ? 'Deleting…' : 'Delete', isDisabled: busy !== '',
                 onClick: () => void removeAsset(asset)},
              ]} />
            </HStack>
          </Card>
        ))}
      </Grid>
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
  const [attachedRefs, setAttachedRefs] = useState<string[]>([]);
  const [library, setLibrary] = useState<Asset[]>([]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [when, setWhen] = useState('');
  const [month, setMonth] = useState(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), 1); });
  const [providers, setProviders] = useState<Record<string, boolean>>({});
  const [role, setRole] = useState('');

  async function load() {
    try {
      const [a, p, status, me, media] = await Promise.all([
        api('/owner/social/accounts'), api('/owner/social/posts'), api('/owner/social/status'),
        api('/owner/me'), api('/owner/media/assets').catch(() => []),
      ]);
      setAccounts(a as Account[]); setPosts(p as Post[]);
      // Anything generated on the Media page is offered here, so "it goes to your composer" is true.
      setLibrary((media as Asset[]) || []);
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

  async function upload(source: File | null = file): Promise<string[] | undefined> {
    if (!source) return undefined;
    const response = await fetch('/owner/social/media', {method: 'POST', headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream'}, body: source});
    if (!response.ok) throw new Error('Media upload failed');
    const data = await response.json();
    return ['upload:' + data.id];
  }

  async function attachAsset(id: string) {
    setBusy(true); setStatus('Adding that to your post…');
    try {
      const response = await fetch('/owner/media/assets/' + id + '/file', {headers: {Authorization: 'Bearer ' + token}});
      if (!response.ok) throw new Error('Media not available.');
      const refs = (await upload(new File([await response.blob()], 'asset', {type: response.headers.get('content-type') || 'image/jpeg'}))) || [];
      setAttachedRefs((current) => [...current, ...refs]);
      setStatus('Added to this post.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not add that media'); }
    setBusy(false);
  }

  async function prepare() {
    setBusy(true); setStatus('');
    try {
      if (!selected.length) throw new Error('Choose at least one connected account');
      const uploaded = await upload();
      // What we promised on the Media page: something you made there can go straight into a post.
      const media = [...(uploaded || []), ...attachedRefs];
      const draft = {content, account_ids: selected, link, hashtags, media, options: {}};
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
          {library.length ? (
            <div style={{margin: '8px 0'}}>
              <span style={{fontSize: 13, opacity: 0.75}}>Or use something you made in Marketing media</span>
              <div style={{display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fill, minmax(84px, 1fr))', marginTop: 6}}>
                {library.slice(0, 8).map((asset) => (
                  <button key={asset.id} type="button" onClick={() => void attachAsset(asset.id)}
                          style={{padding: 0, border: 0, background: 'none', cursor: 'pointer'}}
                          aria-label="Use this in the post">
                    <AssetPreview token={token} id={asset.id} video={asset.kind === 'video'} />
                  </button>
                ))}
              </div>
              {attachedRefs.length ? <p style={{fontSize: 13}}>Attached: {attachedRefs.length}</p> : null}
            </div>
          ) : null}
          <div style={{margin: '12px 0'}}>
            <strong>Accounts</strong>
            {connectable.map((account) => (
              <CheckboxInput label={account.display_name || account.network}
                                 value={selected.includes(account.id)}
                                 onChange={(checked) => setSelected(checked
                                   ? [...selected, account.id]
                                   : selected.filter((id) => id !== account.id))} />
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
      {<StatusLine text={status} />}
    </div>
  );
}


