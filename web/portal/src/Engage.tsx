import {useEffect, useMemo, useState, type ReactNode} from 'react';
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
import {SocialIcon, SOCIAL_NETWORKS, networkLabel} from './SocialIcon';
import {MoreMenu} from '@astryxdesign/core/MoreMenu';
import {Skeleton} from '@astryxdesign/core/Skeleton';
import {useNotify} from './Notify';
import {SegmentedControl, SegmentedControlItem} from '@astryxdesign/core/SegmentedControl';

type Brand = {name: string; accent: string; contact: string; logo?: string | null};
type Asset = {id: string; kind: string; template: string; prompt: string; format: string; created_at: string; original_name?: string};
type Account = {
  id: string;
  network: string;
  external_id?: string;
  display_name: string;
  avatar_url?: string;
  metadata?: Record<string, unknown>;
  needs_reauth?: boolean;
  expires_at?: number | null;
};
type PostResult = {account_id: string; network: string; account_name: string; external_post_id?: string | null; external_url?: string | null; error?: string | null; ok: boolean; at?: string | null};
type Post = {id: string; status: string; content: string; link?: string; hashtags?: string; last_error?: string; scheduled_at?: number | string; created_at?: string; results?: PostResult[]};
type Variant = {account_id: string; account_name: string; network: string; content: string; link?: string; hashtags?: string; media?: string[]; video?: string | null; limit?: number; warnings?: string[]; errors?: string[]};

type MetaInstagramInfo = {
  id: string;
  username: string;
  avatar_url?: string;
  followers_count?: number | null;
  connected_account_id?: string | null;
};

type MetaPageOption = {
  page_id: string;
  name: string;
  avatar_url?: string;
  category?: string;
  followers_count?: number | null;
  fan_count?: number | null;
  tasks?: string[];
  connected_account_id?: string | null;
  linked_business_id?: string;
  linked_business_name?: string;
  business_link_status?: string;
  instagram?: MetaInstagramInfo | null;
};

type MetaPagesResponse = {
  connected: boolean;
  meta_user_name: string;
  granted_scopes: string[];
  selected_business_id: string;
  selected_business_name: string;
  pages: MetaPageOption[];
};

type MetaBusinessOption = {
  id: string;
  name: string;
  avatar_url?: string;
  verification_status?: string;
  owned_page_ids: string[];
  client_page_ids: string[];
};

type MetaBusinessesResponse = {
  connected: boolean;
  granted_business_management: boolean;
  selected_business_id: string;
  selected_business_name: string;
  businesses: MetaBusinessOption[];
};

type BusinessLinkResult = {
  ok: boolean;
  business_id: string;
  business_name: string;
  page_id: string;
  page_name: string;
  relation: string;
  access_status: string;
  linked_at: string;
  message: string;
};

type PageActivityPost = {
  id: string;
  message: string;
  created_time: string;
  permalink_url: string;
  image_url: string;
  likes: number;
  comments: number;
  shares: number;
};

type PageActivityPhoto = {
  id: string;
  caption: string;
  image_url: string;
  link: string;
  created_time: string;
};

type PageActivityResponse = {
  account_id: string;
  page: {
    id: string;
    name: string;
    avatar_url: string;
    category: string;
    link: string;
    followers_count: number | null;
    fan_count: number | null;
    instagram?: MetaInstagramInfo | null;
  };
  totals: {posts: number; likes: number; comments: number; shares: number};
  posts: PageActivityPost[];
  photos: PageActivityPhoto[];
  fetched_at: string;
};

const META_SCOPE_DESCRIPTIONS: Record<string, string> = {
  pages_show_list: 'List your Facebook Pages',
  pages_manage_posts: 'Publish posts to your Facebook Page',
  pages_read_engagement: 'Read Page posts, photos, and engagement',
  business_management: 'Select a Business Portfolio and link Pages',
  instagram_basic: 'Show linked Instagram Professional accounts',
  instagram_content_publish: 'Publish photos and captions to Instagram',
};

function TipWrap({tip, children}: {tip: string; children: ReactNode}) {
  return (
    <span className="c-tip-wrap" title={tip} data-tip={tip}>
      {children}
    </span>
  );
}

function Avatar({src, name, small = false}: {src?: string; name: string; small?: boolean}) {
  const [failedSrc, setFailedSrc] = useState('');
  const cls = small ? 'meta-avatar-sm' : 'meta-avatar';
  if (src && failedSrc !== src) {
    return <img className={cls} src={src} alt={name} referrerPolicy="no-referrer" onError={() => setFailedSrc(src)} />;
  }
  const letter = (name || '?').trim().charAt(0).toUpperCase() || '?';
  return <div className={cls + ' meta-avatar-fallback'} aria-hidden="true">{letter}</div>;
}

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
  const [density, setDensity] = useState<'comfortable' | 'compact'>('comfortable');
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
      // The browser will not put the filename on the wire for a raw-body upload, so send it
      // explicitly; otherwise every tile reads "Image" and two different photos look identical.
      request.setRequestHeader('X-Filename', encodeURIComponent(file.name || ''));
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
      <HStack gap={3} vAlign="center" justify="between" style={{flexWrap: 'wrap'}}>
        <Heading level={2}>Your media</Heading>
        <SegmentedControl label="How much to show per row" value={density}
                          onChange={(value) => setDensity(value as 'comfortable' | 'compact')}>
          <SegmentedControlItem value="comfortable" label="Comfortable" />
          <SegmentedControlItem value="compact" label="Compact" />
        </SegmentedControl>
      </HStack>
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
      <Grid columns={{minWidth: density === 'compact' ? 150 : 260}} gap={density === 'compact' ? 2 : 3}>
        {assets.map((asset) => (
          <Card key={asset.id}>
            <CheckboxInput label="Select" isLabelHidden value={selected.includes(asset.id)}
                           onChange={() => toggleSelected(asset.id)} />
            <AssetPreview token={token} id={asset.id} video={asset.kind === 'video'} />
            <VStack gap={1} hAlign="start">
              <Badge label={asset.kind === 'video' ? 'Video' : 'Image'} />
              {asset.original_name ? (
                <p style={{fontSize: 13, margin: '4px 0 0', overflowWrap: 'anywhere'}} title={asset.original_name}>
                  {asset.original_name}
                </p>
              ) : null}
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
  const [view, setView] = useState<'compose' | 'activity' | 'calendar' | 'posts'>('compose');
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
  const [metaScopes, setMetaScopes] = useState<string[]>([
    'pages_show_list',
    'pages_manage_posts',
    'pages_read_engagement',
    'business_management',
    'instagram_basic',
    'instagram_content_publish',
  ]);
  const [livePublishing, setLivePublishing] = useState(false);
  const [autoPublish, setAutoPublish] = useState(false);
  const [role, setRole] = useState('');

  // Meta App Review flows: Page picker, Business picker + asset link, Page activity, Live publish receipt
  const [metaPages, setMetaPages] = useState<MetaPagesResponse | null>(null);
  const [pageSelectSuccess, setPageSelectSuccess] = useState('');
  const [pageSelectError, setPageSelectError] = useState('');
  const [metaBusinesses, setMetaBusinesses] = useState<MetaBusinessesResponse | null>(null);
  const [selectedBusinessId, setSelectedBusinessId] = useState('');
  const [linkPageId, setLinkPageId] = useState('');
  const [linkRelation, setLinkRelation] = useState<'owned' | 'client'>('owned');
  const [businessLinkResult, setBusinessLinkResult] = useState<BusinessLinkResult | null>(null);
  const [businessLinkError, setBusinessLinkError] = useState('');
  const [activityAccountId, setActivityAccountId] = useState('');
  const [pageActivity, setPageActivity] = useState<PageActivityResponse | null>(null);
  const [publishReceipt, setPublishReceipt] = useState<Post | null>(null);

  const filePreviewUrl = useMemo(() => {
    if (!file || !file.type.startsWith('image/')) return '';
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    if (!filePreviewUrl) return;
    return () => { URL.revokeObjectURL(filePreviewUrl); };
  }, [filePreviewUrl]);

  async function loadMetaContext() {
    try {
      const [pagesRes, bizRes] = await Promise.all([
        api('/owner/social/meta/pages').catch(() => null),
        api('/owner/social/meta/businesses').catch(() => null),
      ]);
      if (pagesRes) {
        const pr = pagesRes as MetaPagesResponse;
        setMetaPages(pr);
        if (pr.pages.length && !linkPageId) {
          setLinkPageId(pr.pages[0].page_id);
        }
      }
      if (bizRes) {
        const br = bizRes as MetaBusinessesResponse;
        setMetaBusinesses(br);
        if (br.selected_business_id) {
          setSelectedBusinessId(br.selected_business_id);
        } else if (br.businesses.length && !selectedBusinessId) {
          setSelectedBusinessId(br.businesses[0].id);
        }
      }
    } catch {
      // Meta context is optional until Facebook Login is completed.
    }
  }

  async function load() {
    try {
      const [a, p, statusRes, me, media] = await Promise.all([
        api('/owner/social/accounts'), api('/owner/social/posts'), api('/owner/social/status'),
        api('/owner/me'), api('/owner/media/assets').catch(() => []),
      ]);
      const acctList = a as Account[];
      setAccounts(acctList);
      setPosts(p as Post[]);
      // Anything uploaded on the Media page is offered here in the composer.
      setLibrary((media as Asset[]) || []);
      const s = statusRes as {providers?: Record<string, boolean>; live_publishing?: boolean; meta_scopes?: string[]};
      setProviders(s.providers || {});
      setLivePublishing(Boolean(s.live_publishing));
      if (Array.isArray(s.meta_scopes) && s.meta_scopes.length) {
        setMetaScopes(s.meta_scopes);
      }
      setRole((me as {role: string}).role);
      const fbPages = acctList.filter((item) => item.network === 'facebook' && !item.needs_reauth);
      if (fbPages.length && !activityAccountId) {
        setActivityAccountId(fbPages[0].id);
      }
      await loadMetaContext();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load social accounts'); }
  }
  useEffect(() => { void load(); }, [token]);

  function oauthPath(provider: string) {
    if (provider === 'google_business') return '/owner/social/oauth/google';
    if (['facebook', 'instagram'].includes(provider)) return '/owner/social/oauth/meta/' + provider;
    return '/owner/social/oauth/' + provider;
  }

  function disconnectPath(provider: string, accountId: string) {
    if (provider === 'linkedin_organization') return '/owner/social/oauth/linkedin/accounts/' + accountId;
    return oauthPath(provider) + '/accounts/' + accountId;
  }

  async function renewAccount(account: Account) {
    if (role !== 'owner') { setStatus('Only the business owner can renew account tokens.'); return; }
    setBusy(true); setStatus('');
    try {
      await api('/owner/social/oauth/renew/' + account.id, 'POST');
      setStatus((account.display_name || networkLabel(account.network)) + ' token renewed.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not renew token; reconnect the account.'); }
    setBusy(false);
  }

  async function disconnectAccount(account: Account) {
    if (role !== 'owner') { setStatus('Only the business owner can disconnect accounts.'); return; }
    if (!window.confirm('Disconnect ' + (account.display_name || networkLabel(account.network)) + '?')) return;
    setBusy(true); setStatus('');
    try {
      await api(disconnectPath(account.network, account.id), 'DELETE');
      setSelected((current) => current.filter((id) => id !== account.id));
      setStatus((account.display_name || networkLabel(account.network)) + ' disconnected.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not disconnect account'); }
    setBusy(false);
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
          setStatus(provider === 'facebook' || provider === 'instagram'
            ? 'Facebook Login complete. Select your Page, Business Portfolio, or Page activity below.'
            : provider.replaceAll('_', ' ') + ' connected.');
          await load();
        } catch (e) { setStatus(e instanceof Error ? e.message : 'Connection failed'); }
      };
      if (channel) channel.onmessage = (event) => { void finish(event.data); };
      window.addEventListener('message', (event) => {
        if (event.origin === location.origin && event.data?.type === 'concierge-social-oauth') void finish(event.data);
      });
      popup.location.href = url.href;
      setStatus('Continue in the provider window. Authorize the permissions for this business.');
    } catch (e) {
      try { popup.close(); } catch { /* ignore */ }
      setStatus(e instanceof Error ? e.message : 'Connection unavailable');
    }
  }

  async function refreshMetaPages() {
    setBusy(true); setStatus('');
    try {
      const res = await api('/owner/social/meta/pages') as MetaPagesResponse;
      setMetaPages(res);
      if (res.pages.length && !linkPageId) setLinkPageId(res.pages[0].page_id);
      setStatus('Loaded ' + res.pages.length + ' authorized Facebook Page' + (res.pages.length === 1 ? '' : 's') + '.');
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load Facebook Pages');
    }
    setBusy(false);
  }

  async function selectMetaPage(page: MetaPageOption) {
    if (role !== 'owner') {
      const msg = 'Only the business owner can select a Facebook Page.';
      setPageSelectError(msg);
      setStatus(msg);
      return;
    }
    setBusy(true); setStatus(''); setPageSelectSuccess(''); setPageSelectError('');
    try {
      const res = await api('/owner/social/meta/pages/select', 'POST', {
        page_id: page.page_id,
        include_instagram: true,
      }) as {
        ok: boolean;
        message: string;
        facebook_account_id: string;
        instagram_account_id?: string | null;
      };
      setPageSelectSuccess(res.message);
      setStatus(res.message);
      const nextSelected = [res.facebook_account_id, ...(res.instagram_account_id ? [res.instagram_account_id] : [])];
      setSelected(nextSelected);
      setActivityAccountId(res.facebook_account_id);
      setLinkPageId(page.page_id);
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Could not select Facebook Page';
      setPageSelectError(msg);
      setStatus(msg);
    }
    setBusy(false);
  }

  async function refreshMetaBusinesses() {
    setBusy(true); setStatus('');
    try {
      const res = await api('/owner/social/meta/businesses') as MetaBusinessesResponse;
      setMetaBusinesses(res);
      if (res.businesses.length && !selectedBusinessId) {
        setSelectedBusinessId(res.selected_business_id || res.businesses[0].id);
      }
      setStatus('Loaded ' + res.businesses.length + ' Meta Business Portfolio' + (res.businesses.length === 1 ? '' : 's') + '.');
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load Meta Business Portfolios');
    }
    setBusy(false);
  }

  async function linkPageToBusiness() {
    if (role !== 'owner') {
      const msg = 'Only the business owner can link a Page to a Business Portfolio.';
      setBusinessLinkError(msg);
      setStatus(msg);
      return;
    }
    if (!selectedBusinessId || !linkPageId) {
      const msg = 'Choose both a Business Portfolio and a Facebook Page first.';
      setBusinessLinkError(msg);
      setStatus(msg);
      return;
    }
    setBusy(true); setStatus(''); setBusinessLinkResult(null); setBusinessLinkError('');
    try {
      const res = await api('/owner/social/meta/businesses/link-page', 'POST', {
        business_id: selectedBusinessId,
        page_id: linkPageId,
        relation: linkRelation,
      }) as BusinessLinkResult;
      setBusinessLinkResult(res);
      setStatus(res.message);
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Could not link Page to Business Portfolio';
      setBusinessLinkError(msg);
      setStatus(msg);
    }
    setBusy(false);
  }

  async function loadPageActivity(targetId?: string) {
    const id = targetId || activityAccountId;
    if (!id) {
      setStatus('Select a connected Facebook Page to view Page activity.');
      return;
    }
    setBusy(true); setStatus('');
    try {
      const res = await api('/owner/social/meta/pages/' + id + '/activity') as PageActivityResponse;
      setPageActivity(res);
      setView('activity');
      setStatus('Loaded Page activity for ' + res.page.name + ' (' + res.totals.posts + ' recent posts).');
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load Page activity');
    }
    setBusy(false);
  }

  async function upload(source: File | null = file): Promise<string[] | undefined> {
    if (!source) return undefined;
    const response = await fetch('/owner/social/media', {method: 'POST', headers: {Authorization: 'Bearer ' + token, 'Content-Type': 'application/octet-stream'}, body: source});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
    return ['upload:' + data.id];
  }

  async function attachAsset(id: string) {
    setBusy(true); setStatus('Adding media to your post…');
    try {
      const response = await fetch('/owner/media/assets/' + id + '/file', {headers: {Authorization: 'Bearer ' + token}});
      if (!response.ok) throw new Error('Media not available.');
      const refs = (await upload(new File([await response.blob()], 'asset', {type: response.headers.get('content-type') || 'image/jpeg'}))) || [];
      setAttachedRefs((current) => [...current, ...refs]);
      setStatus('Added media to this post.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not add that media'); }
    setBusy(false);
  }

  async function prepare() {
    setBusy(true); setStatus('');
    try {
      if (!selected.length) throw new Error('Choose at least one connected account');
      const uploaded = await upload();
      const media = [...(uploaded || []), ...attachedRefs];
      const draft = {content, account_ids: selected, link, hashtags, media, options: {}};
      const result = await api('/owner/social/compose', 'POST', draft) as Variant[];
      setVariants(result);
      setStatus('Previews ready. Review each network version before publishing or scheduling.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Compose failed'); }
    setBusy(false);
  }

  async function publishSelectedNow() {
    if (role !== 'owner') { setStatus('Only the business owner can publish posts immediately.'); return; }
    setBusy(true); setStatus(''); setPublishReceipt(null);
    try {
      if (!selected.length) throw new Error('Select at least one connected Facebook Page or Instagram account');
      if (!content.trim()) throw new Error('Enter a post caption before publishing');
      const uploaded = await upload();
      const media = [...(uploaded || []), ...attachedRefs];
      const saved = await api('/owner/social/posts', 'POST', {
        content: content.trim(),
        account_ids: selected,
        link: link.trim(),
        hashtags: hashtags.trim(),
        media,
        options: {},
      }) as {id: string};
      const published = await api('/owner/social/posts/' + saved.id + '/publish-now', 'POST') as Post;
      setPublishReceipt(published);
      setStatus(published.status === 'published'
        ? 'Published to selected accounts. Use the live links below to verify on Facebook and Instagram.'
        : (published.last_error || 'Publish completed with status: ' + published.status));
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not publish post');
    }
    setBusy(false);
  }

  async function saveVariant(variant: Variant, mode: 'draft' | 'submit' | 'schedule' | 'publish_now') {
    setBusy(true); setStatus('');
    try {
      const media = variant.media || [];
      const draft = {content: variant.content, account_ids: [variant.account_id], link: variant.link || '', hashtags: variant.hashtags || '', media, video: variant.video || null, options: {}};
      const saved = await api('/owner/social/posts', 'POST', draft) as {id: string};
      if (mode === 'draft') {
        setStatus('Draft saved. Submit it for approval when ready.');
      } else if (mode === 'submit') {
        await api('/owner/social/posts/' + saved.id + '/submit', 'POST');
        setStatus('Submitted for owner approval. Approve it in Your posts below to publish.');
      } else if (mode === 'publish_now' && livePublishing) {
        const published = await api('/owner/social/posts/' + saved.id + '/publish-now', 'POST') as Post;
        setPublishReceipt(published);
        setStatus(published.status === 'published'
          ? 'Published live. Open the live post link below to verify.'
          : (published.last_error || 'Publish completed with status: ' + published.status));
      } else {
        await api('/owner/social/posts/' + saved.id + '/submit', 'POST');
        const at = mode === 'publish_now'
          ? Math.floor(Date.now() / 1000)
          : (when ? Math.floor(new Date(when).getTime() / 1000) : Math.floor(Date.now() / 1000) + 3600);
        const approval = await api('/owner/social/posts/' + saved.id + '/approval-request', 'POST', {scheduled_at: at}) as {token: string};
        await api('/owner/social/approvals/' + approval.token + '/approve', 'POST');
        setStatus(livePublishing
          ? (mode === 'publish_now' ? 'Approved and queued for immediate live publishing.' : 'Approved and scheduled for live publishing.')
          : 'Approved and scheduled in Concierge (live publishing is currently paused).');
      }
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the post'); }
    setBusy(false);
  }

  async function submitPostForApproval(postId: string) {
    setBusy(true); setStatus('');
    try {
      await api('/owner/social/posts/' + postId + '/submit', 'POST');
      setStatus('Post submitted for owner approval.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not submit post'); }
    setBusy(false);
  }

  async function decidePost(postId: string, action: 'schedule' | 'publish_now' | 'reject') {
    if (role !== 'owner') { setStatus('Only the business owner can approve or reject posts.'); return; }
    setBusy(true); setStatus('');
    try {
      if (action === 'publish_now' && livePublishing) {
        const published = await api('/owner/social/posts/' + postId + '/publish-now', 'POST') as Post;
        setPublishReceipt(published);
        setStatus(published.status === 'published'
          ? 'Approved and published live. Open the live post link below to verify.'
          : (published.last_error || 'Publish completed with status: ' + published.status));
        await load();
        setBusy(false);
        return;
      }
      const at = action === 'publish_now'
        ? Math.floor(Date.now() / 1000)
        : (when ? Math.floor(new Date(when).getTime() / 1000) : Math.floor(Date.now() / 1000) + 3600);
      const approval = await api('/owner/social/posts/' + postId + '/approval-request', 'POST', {scheduled_at: at}) as {token: string};
      if (action === 'reject') {
        await api('/owner/social/approvals/' + approval.token + '/reject', 'POST');
        setStatus('Post returned to draft.');
      } else {
        await api('/owner/social/approvals/' + approval.token + '/approve', 'POST');
        setStatus(livePublishing
          ? (action === 'publish_now' ? 'Approved for immediate live publishing.' : 'Approved and scheduled for live publishing.')
          : 'Approved and scheduled in Concierge (live publishing is currently paused).');
      }
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not update post approval'); }
    setBusy(false);
  }

  const connectable = accounts.filter((a) => !a.needs_reauth && a.network !== 'bluesky');
  const connectedFacebookPages = connectable.filter((a) => a.network === 'facebook');
  const connectedMetaPublishIds = connectable
    .filter((a) => a.network === 'facebook' || a.network === 'instagram')
    .map((a) => a.id);
  const selectedBusiness = (metaBusinesses?.businesses || []).find((b) => b.id === selectedBusinessId) || null;

  return (
    <div>
      <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap', marginBottom: 8}}>
        <p style={{margin: 0}}>Connect Facebook Pages and Instagram accounts, manage Business Portfolio links, review Page activity, and publish approved posts for {brand.name || 'your business'}.</p>
        <Badge label={livePublishing ? 'Live publishing enabled' : 'Drafts & approvals only'} variant={livePublishing ? 'success' : 'neutral'} />
      </HStack>

      <Card>
        <HStack gap={2} vAlign="center" justify="between" style={{flexWrap: 'wrap'}}>
          <div>
            <Heading level={2}>Meta Facebook Login (Pages, Instagram &amp; Business)</Heading>
            <p style={{margin: '4px 0 0', fontSize: 13, opacity: 0.85}}>
              Uses standard Facebook Login (user OAuth 2.0) to authorize your Facebook Pages, linked Instagram Professional accounts, Page engagement insights, and Meta Business Portfolios.
            </p>
          </div>
          <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
            {metaPages?.connected ? (
              <Badge
                label={'Signed in' + (metaPages.meta_user_name ? ': ' + metaPages.meta_user_name : ' with Facebook')}
                variant="success"
              />
            ) : null}
            <TipWrap tip="Sign in with Facebook Login and grant the 6 required permissions for Pages, Instagram publishing, Page activity, and Business management.">
              <Button
                label={metaPages?.connected ? 'Reconnect with Facebook' : 'Continue with Facebook'}
                variant="primary"
                isDisabled={busy || !providers.facebook || role !== 'owner'}
                onClick={() => void connect('facebook')}
              />
            </TipWrap>
          </HStack>
        </HStack>
        <div className="meta-scope-list" aria-label="Requested Meta permissions">
          {metaScopes.map((scope) => {
            const granted = Boolean(metaPages?.granted_scopes?.includes(scope));
            return (
              <span
                key={scope}
                className="meta-scope-chip"
                title={META_SCOPE_DESCRIPTIONS[scope] || scope}>
                {granted ? '✓ ' : ''}<code>{scope}</code>
                {META_SCOPE_DESCRIPTIONS[scope] ? ' — ' + META_SCOPE_DESCRIPTIONS[scope] : ''}
              </span>
            );
          })}
        </div>
      </Card>

      <Card>
        <HStack gap={2} vAlign="center" justify="between" style={{flexWrap: 'wrap'}}>
          <div>
            <Heading level={2}>Facebook Page &amp; Instagram picker</Heading>
            <p style={{margin: '4px 0 0', fontSize: 13, opacity: 0.85}}>
              Choose which authorized Facebook Page and linked Instagram Professional account to activate for publishing and engagement activity.
            </p>
          </div>
          <TipWrap tip="Reload authorized Facebook Pages and linked Instagram Professional accounts from Meta.">
            <Button label="Refresh Pages" variant="secondary" isDisabled={busy} onClick={() => void refreshMetaPages()} />
          </TipWrap>
        </HStack>

        {pageSelectSuccess ? (
          <div className="meta-success-box" role="status">
            <HStack gap={2} vAlign="center">
              <Badge label="Page selected" variant="success" />
              <strong>{pageSelectSuccess}</strong>
            </HStack>
          </div>
        ) : null}
        {pageSelectError ? (
          <div className="meta-error-box" role="alert">
            <HStack gap={2} vAlign="center">
              <Badge label="Selection failed" variant="error" />
              <strong>{pageSelectError}</strong>
            </HStack>
          </div>
        ) : null}

        {metaPages?.pages?.length ? (
          <div className="meta-picker-grid">
            {metaPages.pages.map((page) => {
              const isConnected = Boolean(page.connected_account_id);
              return (
                <div key={page.page_id} className={'meta-page-item' + (isConnected ? ' is-selected' : '')}>
                  <HStack gap={2} vAlign="center">
                    <Avatar src={page.avatar_url} name={page.name} />
                    <div style={{flex: 1, minWidth: 0}}>
                      <strong style={{display: 'block', overflowWrap: 'anywhere'}}>{page.name}</strong>
                      <span style={{fontSize: 12, opacity: 0.78}}>
                        {page.category ? page.category + ' · ' : ''}Page ID: {page.page_id}
                        {typeof page.followers_count === 'number' ? ' · ' + page.followers_count.toLocaleString() + ' followers' : ''}
                      </span>
                    </div>
                    {isConnected ? <Badge label="Connected" variant="success" /> : null}
                  </HStack>

                  {page.instagram ? (
                    <HStack gap={2} vAlign="center" style={{padding: '8px 10px', borderRadius: 10, background: 'var(--c-page)'}}>
                      <Avatar src={page.instagram.avatar_url} name={page.instagram.username} small />
                      <span style={{fontSize: 12.5}}>
                        <strong>Instagram:</strong> @{page.instagram.username}
                        {typeof page.instagram.followers_count === 'number'
                          ? ' (' + page.instagram.followers_count.toLocaleString() + ' followers)'
                          : ''}
                      </span>
                      {page.instagram.connected_account_id ? <Badge label="IG ready" variant="info" /> : null}
                    </HStack>
                  ) : (
                    <span style={{fontSize: 12, opacity: 0.7}}>No linked Instagram Professional account on this Page.</span>
                  )}

                  {page.linked_business_name ? (
                    <span style={{fontSize: 12}}>
                      <strong>Business:</strong> {page.linked_business_name} ({page.business_link_status || 'Linked'})
                    </span>
                  ) : null}

                  <HStack gap={2} style={{flexWrap: 'wrap'}}>
                    <TipWrap tip="Select this Facebook Page and its linked Instagram account for posting and Page activity.">
                      <Button
                        label={isConnected ? 'Selected — use Page' : 'Select Page'}
                        variant={isConnected ? 'secondary' : 'primary'}
                        isDisabled={busy || role !== 'owner'}
                        onClick={() => void selectMetaPage(page)}
                      />
                    </TipWrap>
                    {page.connected_account_id ? (
                      <TipWrap tip="Load recent posts, photos, followers, and engagement counts for this Facebook Page.">
                        <Button
                          label="View Page activity"
                          variant="ghost"
                          isDisabled={busy}
                          onClick={() => {
                            setActivityAccountId(page.connected_account_id || '');
                            void loadPageActivity(page.connected_account_id || '');
                          }}
                        />
                      </TipWrap>
                    ) : null}
                  </HStack>
                </div>
              );
            })}
          </div>
        ) : (
          <p style={{marginTop: 10, fontSize: 13, opacity: 0.8}}>
            Click <strong>Continue with Facebook</strong> above to load your authorized Facebook Pages and linked Instagram accounts.
          </p>
        )}
      </Card>

      <Card>
        <HStack gap={2} vAlign="center" justify="between" style={{flexWrap: 'wrap'}}>
          <div>
            <Heading level={2}>Meta Business Portfolio (Link Page to business)</Heading>
            <p style={{margin: '4px 0 0', fontSize: 13, opacity: 0.85}}>
              Select a Meta Business Portfolio and link or claim a Facebook Page under that business using <code>business_management</code>.
            </p>
          </div>
          <TipWrap tip="Fetch Meta Business Portfolios accessible to your Facebook login.">
            <Button label="Load Businesses" variant="secondary" isDisabled={busy} onClick={() => void refreshMetaBusinesses()} />
          </TipWrap>
        </HStack>

        {metaBusinesses?.businesses?.length ? (
          <div style={{display: 'grid', gap: 12, marginTop: 12}}>
            <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
              <label style={{display: 'grid', gap: 4, fontSize: 13}}>
                <span>Business Portfolio</span>
                <select
                  aria-label="Select Meta Business Portfolio"
                  className="meta-select"
                  value={selectedBusinessId}
                  onChange={(e) => setSelectedBusinessId(e.target.value)}>
                  {metaBusinesses.businesses.map((biz) => (
                    <option key={biz.id} value={biz.id}>
                      {biz.name} ({biz.id}){biz.verification_status ? ' — ' + biz.verification_status : ''}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{display: 'grid', gap: 4, fontSize: 13}}>
                <span>Facebook Page to link</span>
                <select
                  aria-label="Select Facebook Page to link"
                  className="meta-select"
                  value={linkPageId}
                  onChange={(e) => setLinkPageId(e.target.value)}>
                  {(metaPages?.pages || []).map((page) => (
                    <option key={page.page_id} value={page.page_id}>
                      {page.name} ({page.page_id})
                    </option>
                  ))}
                </select>
              </label>

              <label style={{display: 'grid', gap: 4, fontSize: 13}}>
                <span>Asset relationship</span>
                <select
                  aria-label="Select Business asset relationship"
                  className="meta-select"
                  value={linkRelation}
                  onChange={(e) => setLinkRelation(e.target.value as 'owned' | 'client')}>
                  <option value="owned">Owned Page (claim to Business)</option>
                  <option value="client">Client Page (request agency access)</option>
                </select>
              </label>

              <div style={{alignSelf: 'flex-end'}}>
                <TipWrap tip="Link or claim the chosen Facebook Page under the selected Meta Business Portfolio.">
                  <Button
                    label="Link Page to business"
                    variant="primary"
                    isDisabled={busy || role !== 'owner' || !selectedBusinessId || !linkPageId}
                    onClick={() => void linkPageToBusiness()}
                  />
                </TipWrap>
              </div>
            </HStack>

            {selectedBusiness ? (
              <HStack gap={2} vAlign="center" style={{fontSize: 13}}>
                <Avatar src={selectedBusiness.avatar_url} name={selectedBusiness.name} small />
                <span>
                  Selected business: <strong>{selectedBusiness.name}</strong> (ID: {selectedBusiness.id}) · Owned Pages: {selectedBusiness.owned_page_ids.length} · Client Pages: {selectedBusiness.client_page_ids.length}
                </span>
              </HStack>
            ) : null}
          </div>
        ) : (
          <p style={{marginTop: 10, fontSize: 13, opacity: 0.8}}>
            {metaBusinesses?.connected
              ? 'No Meta Business Portfolios were returned for this login. Click Load Businesses after granting business_management.'
              : 'Sign in with Facebook above, then click Load Businesses to select a Meta Business Portfolio and link a Page.'}
          </p>
        )}

        {businessLinkResult ? (
          <div className="meta-success-box" role="status">
            <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
              <Badge label={'Linked: ' + businessLinkResult.access_status} variant="success" />
              <strong>{businessLinkResult.message}</strong>
            </HStack>
            <span style={{fontSize: 12.5}}>
              Business: <strong>{businessLinkResult.business_name}</strong> ({businessLinkResult.business_id}) · Page: <strong>{businessLinkResult.page_name}</strong> ({businessLinkResult.page_id})
            </span>
          </div>
        ) : null}
        {businessLinkError ? (
          <div className="meta-error-box" role="alert">
            <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
              <Badge label="Link failed" variant="error" />
              <strong>{businessLinkError}</strong>
            </HStack>
          </div>
        ) : null}
      </Card>

      <Card>
        <Heading level={2}>Social accounts</Heading>
        <p>Authorize one account at a time on the provider&apos;s own site. A full-colour mark means the network is available for this business; a faded one means setup has not been enabled yet.</p>
        <div className="social-connect">
          {SOCIAL_NETWORKS.map((network) => {
            const linked = accounts.filter((account) => account.network === network.id);
            const enabled = Boolean(providers[network.id]);
            return (
              <div key={network.id} className={'social-connect-card' + (enabled ? '' : ' is-off')}>
                <SocialIcon network={network.id} size={30} />
                <div className="social-connect-copy">
                  <strong>{network.label}</strong>
                  <span>{linked.length
                    ? linked.map((account) => account.display_name || 'Connected').join(' · ')
                    : enabled ? network.note : 'Not enabled for this business yet'}</span>
                </div>
                <HStack gap={1} vAlign="center">
                  {enabled ? (
                    <TipWrap tip={'Authorize ' + network.label + ' via OAuth in a secure popup window.'}>
                      <Button label={linked.length ? 'Add another' : 'Connect'} variant={linked.length ? 'secondary' : 'primary'}
                              isDisabled={busy} onClick={() => void connect(network.id)} />
                    </TipWrap>
                  ) : <Badge label="setup" variant="neutral" />}
                  {role === 'owner' && linked.length && linked[0].needs_reauth ? (
                    <TipWrap tip={'Refresh the expired OAuth token for ' + network.label + '.'}>
                      <Button label="Renew" variant="secondary" isDisabled={busy}
                              onClick={() => void renewAccount(linked[0])} />
                    </TipWrap>
                  ) : null}
                  {role === 'owner' && linked.length ? (
                    <TipWrap tip={'Disconnect ' + (linked[0].display_name || network.label) + ' and remove its stored token.'}>
                      <Button label="Disconnect" variant="ghost" isDisabled={busy}
                              onClick={() => void disconnectAccount(linked[0])} />
                    </TipWrap>
                  ) : null}
                </HStack>
              </div>
            );
          })}
        </div>
        {!Object.values(providers).some(Boolean) ? <p>Account connections are awaiting Trendi setup for this business.</p> : null}
        {role !== 'owner' ? <p>Only the business owner can connect an account.</p> : null}
        {role === 'owner' ? (
          <div style={{marginTop: 10}}>
            <CheckboxInput
              label="Auto-publish approved composer previews (off by default — requires owner approval in Your posts when unchecked)"
              value={autoPublish}
              onChange={setAutoPublish}
            />
          </div>
        ) : null}
      </Card>

      {!accounts.length ? <Card><p>No social accounts are connected yet.</p><p>Sign in with Facebook or choose a network above; it appears here once connected.</p></Card> : null}

      {accounts.length ? (
        <Card>
          <HStack gap={2} vAlign="center" justify="between" style={{flexWrap: 'wrap'}}>
            <Heading level={2}>New post composer (Facebook &amp; Instagram)</Heading>
            {connectedMetaPublishIds.length ? (
              <TipWrap tip="Check both your connected Facebook Page and linked Instagram Professional account at once.">
                <Button
                  label="Select Facebook & Instagram"
                  variant="secondary"
                  isDisabled={busy}
                  onClick={() => setSelected(connectedMetaPublishIds)}
                />
              </TipWrap>
            ) : null}
          </HStack>
          <TextArea label="Post caption" value={content} onChange={setContent} rows={5} />
          <TextInput label="Link (optional)" type="url" value={link} onChange={setLink} />
          <TextInput label="Hashtags (optional)" value={hashtags} onChange={setHashtags} />
          <FileInput label="Image or video (required for Instagram)" value={file} onChange={(v) => setFile(Array.isArray(v) ? (v[0] || null) : ((v as File) || null))} accept="image/*,video/*" />
          {filePreviewUrl ? (
            <div style={{marginTop: 8}}>
              <img src={filePreviewUrl} alt="Selected media preview" style={{maxWidth: 180, maxHeight: 180, borderRadius: 10, objectFit: 'cover'}} />
            </div>
          ) : null}
          {library.length ? (
            <div style={{margin: '8px 0'}}>
              <span style={{fontSize: 13, opacity: 0.75}}>Or attach media from your Marketing media library</span>
              <div style={{display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fill, minmax(84px, 1fr))', marginTop: 6}}>
                {library.slice(0, 8).map((asset) => (
                  <button key={asset.id} type="button" onClick={() => void attachAsset(asset.id)}
                          style={{padding: 0, border: 0, background: 'none', cursor: 'pointer'}}
                          aria-label={'Use ' + (asset.original_name || 'this media') + ' in the post'}
                          title={'Attach ' + (asset.original_name || 'library media') + ' to this post'}>
                    <AssetPreview token={token} id={asset.id} video={asset.kind === 'video'} />
                  </button>
                ))}
              </div>
              {attachedRefs.length ? <p style={{fontSize: 13}}>Attached media items: {attachedRefs.length}</p> : null}
            </div>
          ) : null}
          <div style={{margin: '12px 0'}}>
            <strong>Target accounts</strong>
            {connectable.map((account) => (
              <div key={account.id} style={{display: 'flex', alignItems: 'center', gap: 10, padding: '4px 0'}}>
                <SocialIcon network={account.network} size={20} />
                {account.avatar_url ? <Avatar src={account.avatar_url} name={account.display_name} small /> : null}
                <CheckboxInput label={(account.display_name || networkLabel(account.network)) + ' (' + networkLabel(account.network) + ')'}
                               value={selected.includes(account.id)}
                               onChange={(checked) => setSelected(checked
                                 ? [...selected, account.id]
                                 : selected.filter((id) => id !== account.id))} />
              </div>
            ))}
          </div>
          <HStack gap={2} style={{flexWrap: 'wrap'}}>
            <TipWrap tip="Generate per-network previews and validate character limits and media rules before posting.">
              <Button label={busy ? 'Preparing…' : 'Prepare previews'} variant="secondary" isDisabled={busy} onClick={prepare} />
            </TipWrap>
            {role === 'owner' ? (
              <TipWrap tip="Approve and immediately publish this caption and image to every selected Facebook Page and Instagram account, returning direct links to the live posts.">
                <Button
                  label={busy ? 'Publishing…' : 'Publish to selected accounts now'}
                  variant="primary"
                  isDisabled={busy || !selected.length || !content.trim()}
                  onClick={() => void publishSelectedNow()}
                />
              </TipWrap>
            ) : null}
          </HStack>

          {publishReceipt ? (
            <div className="meta-success-box" role="status">
              <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
                <Badge
                  label={publishReceipt.status === 'published' ? 'Published successfully' : publishReceipt.status}
                  variant={publishReceipt.status === 'published' ? 'success' : 'error'}
                />
                <strong>Live publish summary</strong>
              </HStack>
              <p style={{margin: 0, whiteSpace: 'pre-wrap', fontSize: 13}}>{publishReceipt.content}</p>
              {publishReceipt.results?.map((r) => (
                <HStack key={r.account_id + ':' + String(r.ok)} gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
                  <SocialIcon network={r.network} size={18} />
                  <strong>{r.account_name || networkLabel(r.network)}</strong>
                  {r.ok ? (
                    <>
                      <Badge label="Live" variant="success" />
                      {r.external_url ? (
                        <a href={r.external_url} target="_blank" rel="noopener noreferrer">
                          View live {networkLabel(r.network)} post ↗
                        </a>
                      ) : (
                        <span>Published (ID: {r.external_post_id})</span>
                      )}
                    </>
                  ) : (
                    <span role="alert">{r.error || 'Delivery failed'}</span>
                  )}
                </HStack>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}

      {variants.map((variant) => (
        <Card key={variant.account_id}>
          <Heading level={2}>{variant.network.replaceAll('_', ' ')} — {variant.account_name}</Heading>
          <TextArea label="Exact post text" value={variant.content} onChange={(v) => setVariants(variants.map((item) => item.account_id === variant.account_id ? {...item, content: v} : item))} rows={5} />
          <p>{variant.limit ? variant.content.length + ' / ' + variant.limit + ' characters' : ''}</p>
          {variant.errors?.map((error) => <p key={error} role="alert">{error}</p>)}
          <HStack gap={2} style={{flexWrap: 'wrap'}}>
            <TipWrap tip="Save this network post as a draft without publishing.">
              <Button label="Save draft" variant="secondary" isDisabled={busy} onClick={() => void saveVariant(variant, 'draft')} />
            </TipWrap>
            {autoPublish && role === 'owner' ? (
              <>
                <TipWrap tip="Approve and schedule this post for the chosen date and time.">
                  <Button label="Schedule" variant="primary" isDisabled={busy} onClick={() => void saveVariant(variant, 'schedule')} />
                </TipWrap>
                <TipWrap tip="Approve and immediately publish this post to the selected account.">
                  <Button label="Publish now" variant="primary" isDisabled={busy} onClick={() => void saveVariant(variant, 'publish_now')} />
                </TipWrap>
              </>
            ) : (
              <TipWrap tip="Submit this preview for business owner approval before it can publish.">
                <Button label="Submit for owner approval" variant="primary" isDisabled={busy} onClick={() => void saveVariant(variant, 'submit')} />
              </TipWrap>
            )}
          </HStack>
        </Card>
      ))}

      <SegmentedControl label="What to work on" value={view}
                        onChange={(value) => setView(value as 'compose' | 'activity' | 'calendar' | 'posts')}>
        <SegmentedControlItem value="compose" label="Write a post" />
        <SegmentedControlItem value="activity" label="Page activity" />
        <SegmentedControlItem value="calendar" label="Calendar" />
        <SegmentedControlItem value="posts" label="Your posts" />
      </SegmentedControl>

      {view === 'compose' ? (<DateTimeInput label="Schedule time (optional, defaults to one hour from now)" value={(when || undefined) as never} onChange={(value) => setWhen(value || '')} description="Local time; leave blank for one hour from now." />) : null}

      {view === 'activity' ? (
        <Card>
          <HStack gap={2} vAlign="center" justify="between" style={{flexWrap: 'wrap'}}>
            <div>
              <Heading level={2}>Page activity &amp; engagement</Heading>
              <p style={{margin: '4px 0 0', fontSize: 13, opacity: 0.85}}>
                Retrieve followers, recent posts, photos, likes, comments, and shares for a selected Facebook Page using <code>pages_read_engagement</code>.
              </p>
            </div>
            <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap'}}>
              <select
                aria-label="Select Facebook Page for activity"
                className="meta-select"
                value={activityAccountId}
                onChange={(e) => setActivityAccountId(e.target.value)}>
                {connectedFacebookPages.length ? connectedFacebookPages.map((pg) => (
                  <option key={pg.id} value={pg.id}>{pg.display_name}</option>
                )) : <option value="">No connected Facebook Page</option>}
              </select>
              <TipWrap tip="Fetch latest followers, posts, photos, likes, comments, and shares for the selected Facebook Page.">
                <Button
                  label={busy ? 'Loading…' : 'Load Page activity'}
                  variant="primary"
                  isDisabled={busy || !activityAccountId}
                  onClick={() => void loadPageActivity()}
                />
              </TipWrap>
            </HStack>
          </HStack>

          {pageActivity ? (
            <div style={{marginTop: 14, display: 'grid', gap: 14}}>
              <HStack gap={2} vAlign="center" justify="between" style={{flexWrap: 'wrap', padding: 14, borderRadius: 14, background: 'var(--c-surface)'}}>
                <HStack gap={2} vAlign="center">
                  <Avatar src={pageActivity.page.avatar_url} name={pageActivity.page.name} />
                  <div>
                    <strong style={{fontSize: 16, display: 'block'}}>{pageActivity.page.name}</strong>
                    <span style={{fontSize: 12.5, opacity: 0.8}}>
                      {pageActivity.page.category ? pageActivity.page.category + ' · ' : ''}Facebook Page ID: {pageActivity.page.id}
                      {pageActivity.page.instagram ? ' · Instagram: @' + pageActivity.page.instagram.username : ''}
                    </span>
                  </div>
                </HStack>
                {pageActivity.page.link ? (
                  <a href={pageActivity.page.link} target="_blank" rel="noopener noreferrer">Open Facebook Page ↗</a>
                ) : null}
              </HStack>

              <div className="c-kpis">
                <div className="c-kpi">
                  <strong>{typeof pageActivity.page.followers_count === 'number' ? pageActivity.page.followers_count.toLocaleString() : '—'}</strong>
                  <span>Page followers</span>
                </div>
                <div className="c-kpi">
                  <strong>{typeof pageActivity.page.fan_count === 'number' ? pageActivity.page.fan_count.toLocaleString() : '—'}</strong>
                  <span>Page likes</span>
                </div>
                <div className="c-kpi">
                  <strong>{pageActivity.totals.posts}</strong>
                  <span>Recent posts</span>
                </div>
                <div className="c-kpi">
                  <strong>{pageActivity.totals.likes}</strong>
                  <span>Post likes</span>
                </div>
                <div className="c-kpi">
                  <strong>{pageActivity.totals.comments}</strong>
                  <span>Comments</span>
                </div>
                <div className="c-kpi">
                  <strong>{pageActivity.totals.shares}</strong>
                  <span>Shares</span>
                </div>
              </div>

              <div>
                <Heading level={3}>Recent posts on {pageActivity.page.name}</Heading>
                {pageActivity.posts.length ? (
                  <div style={{display: 'grid', gap: 10, marginTop: 8}}>
                    {pageActivity.posts.map((item) => (
                      <div key={item.id} className="meta-activity-post">
                        {item.image_url ? <img src={item.image_url} alt="Post attachment" referrerPolicy="no-referrer" /> : null}
                        <div style={{flex: 1, minWidth: 0}}>
                          <p style={{margin: '0 0 6px', whiteSpace: 'pre-wrap'}}>{item.message || '(Photo or status update)'}</p>
                          <HStack gap={2} vAlign="center" style={{flexWrap: 'wrap', fontSize: 12.5}}>
                            <Badge label={'Likes: ' + item.likes} variant="neutral" />
                            <Badge label={'Comments: ' + item.comments} variant="neutral" />
                            <Badge label={'Shares: ' + item.shares} variant="neutral" />
                            {item.created_time ? <Timestamp value={item.created_time} format="date_time" type="supporting" /> : null}
                            {item.permalink_url ? (
                              <a href={item.permalink_url} target="_blank" rel="noopener noreferrer">View on Facebook ↗</a>
                            ) : null}
                          </HStack>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{fontSize: 13, opacity: 0.8}}>No recent posts were returned for {pageActivity.page.name}.</p>
                )}
              </div>

              <div>
                <Heading level={3}>Recent Page photos</Heading>
                {pageActivity.photos.length ? (
                  <div style={{display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', marginTop: 8}}>
                    {pageActivity.photos.map((photo) => (
                      <a key={photo.id} href={photo.link || photo.image_url} target="_blank" rel="noopener noreferrer" style={{display: 'block'}}>
                        <img src={photo.image_url} alt={photo.caption || 'Page photo'} referrerPolicy="no-referrer" style={{width: '100%', aspectRatio: '1 / 1', objectFit: 'cover', borderRadius: 10}} />
                      </a>
                    ))}
                  </div>
                ) : (
                  <p style={{fontSize: 13, opacity: 0.8, marginTop: 6}}>No photos yet</p>
                )}
              </div>
            </div>
          ) : (
            <p style={{marginTop: 12, fontSize: 13, opacity: 0.8}}>
              Choose a connected Facebook Page and click <strong>Load Page activity</strong> to view Page followers, recent posts, and engagement counts.
            </p>
          )}
        </Card>
      ) : null}

      {view === 'calendar' ? (
        <>
          <Heading level={2}>Calendar</Heading>
          <div style={{display: 'flex', alignItems: 'center', gap: 12, margin: '8px 0'}}>
            <TipWrap tip="Show the previous month.">
              <Button label="←" variant="ghost" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))} />
            </TipWrap>
            <strong>{month.toLocaleString('en-NZ', {month: 'long', year: 'numeric'})}</strong>
            <TipWrap tip="Show the next month.">
              <Button label="→" variant="ghost" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))} />
            </TipWrap>
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
        </>
      ) : null}

      {view === 'posts' ? (
        <>
          <Heading level={2}>Your posts</Heading>
          <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))'}}>
            {posts.map((post) => (
              <Card key={post.id}>
                <Badge label={post.status.replaceAll('_', ' ')} variant={post.status === 'published' ? 'success' : post.status === 'failed' ? 'error' : 'neutral'} />
                <p style={{whiteSpace: 'pre-wrap'}}>{[post.content, post.link, post.hashtags].filter(Boolean).join('\n')}</p>
                {post.last_error ? <p role="alert">{post.last_error}</p> : null}
                {post.results && post.results.length ? (
                  <div style={{marginTop: 6, fontSize: 12}}>
                    {post.results.map((r) => (
                      <div key={r.account_id + ':' + String(r.ok)} style={{marginTop: 3}}>
                        <strong>{r.account_name || networkLabel(r.network)}</strong>:{' '}
                        {r.ok ? (
                          r.external_url
                            ? <a href={r.external_url} target="_blank" rel="noopener noreferrer">View live post ↗</a>
                            : 'Published'
                        ) : (
                          <span role="alert">{r.error || 'Delivery failed'}</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}
                <HStack gap={2} style={{flexWrap: 'wrap', marginTop: 8}}>
                  {post.status === 'draft' ? (
                    <TipWrap tip="Submit this draft for business owner approval.">
                      <Button label="Submit for approval" variant="secondary" isDisabled={busy} onClick={() => void submitPostForApproval(post.id)} />
                    </TipWrap>
                  ) : null}
                  {post.status === 'pending_approval' && role === 'owner' ? (
                    <>
                      <TipWrap tip="Approve this post and schedule it for the selected time.">
                        <Button label="Approve & schedule" variant="primary" isDisabled={busy} onClick={() => void decidePost(post.id, 'schedule')} />
                      </TipWrap>
                      <TipWrap tip="Approve and immediately publish this post live.">
                        <Button label="Approve & publish now" variant="primary" isDisabled={busy} onClick={() => void decidePost(post.id, 'publish_now')} />
                      </TipWrap>
                      <TipWrap tip="Return this post to draft status without publishing.">
                        <Button label="Reject" variant="ghost" isDisabled={busy} onClick={() => void decidePost(post.id, 'reject')} />
                      </TipWrap>
                    </>
                  ) : null}
                </HStack>
              </Card>
            ))}
            {!posts.length ? <div className="c-empty"><strong>No drafts yet</strong><p>Nothing is published until you approve it. Write a post above and save or publish it here.</p></div> : null}
          </div>
        </>
      ) : null}
      {<StatusLine text={status} />}
    </div>
  );
}


