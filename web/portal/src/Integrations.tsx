import {useEffect, useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {TextInput} from '@astryxdesign/core/TextInput';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {createApi} from './api';
import {StatusLine} from './StatusLine';

type IntegrationItem = {
  provider: string;
  label: string;
  enabled: boolean;
  method: string;
  unavailable_reason: string;
  status: string;
  account: string;
  last_error: string;
  last_sync_at: string | null;
};

type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  scope: string;
  created_at: string;
  last_used_at: string | null;
  revoked: boolean;
};

type MetaChannelRow = {
  id: string;
  channel: 'whatsapp' | 'messenger' | 'instagram';
  external_id: string;
  page_id?: string;
  waba_id?: string;
  display_name?: string;
  webhook_subscribed?: boolean;
  enabled: boolean;
  created_at: string;
};

type MetaOverview = {
  platform_enabled: boolean;
  unavailable_reason: string;
  wa_embedded_signup?: {enabled: boolean; unavailable_reason: string};
  channels: MetaChannelRow[];
};

type WebhookEventRow = {
  id: number;
  event: string;
  attempts: number;
  delivered_at: string | null;
  last_error: string | null;
  created_at: string;
};

export function Integrations({token}: {token: string}) {
  const api = createApi(token);
  const [items, setItems] = useState<IntegrationItem[]>([]);
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [metaOverview, setMetaOverview] = useState<MetaOverview | null>(null);
  const [webhookEvents, setWebhookEvents] = useState<WebhookEventRow[]>([]);
  const [keyName, setKeyName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [sm8Key, setSm8Key] = useState('');
  const [teamWebhook, setTeamWebhook] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [intRes, keyRes, hookRes, metaRes, evRes] = await Promise.all([
        api('/owner/integrations') as Promise<{integrations: IntegrationItem[]}>,
        api('/owner/api-keys') as Promise<{keys: ApiKeyRow[]}>,
        api('/owner/team-chat-webhook').catch(() => ({url: ''})) as Promise<{url?: string}>,
        api('/owner/meta-messaging').catch(() => null) as Promise<MetaOverview | null>,
        api('/owner/webhooks/events?limit=20').catch(() => ({events: []})) as Promise<{events?: WebhookEventRow[]}>,
      ]);
      setItems(intRes.integrations || []);
      setKeys(keyRes.keys || []);
      setTeamWebhook(hookRes.url || '');
      setMetaOverview(metaRes);
      setWebhookEvents(evRes.events || []);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load integrations');
    }
  }

  async function testWebhook() {
    setBusy(true);
    setStatus('');
    try {
      const res = await api('/owner/webhooks/test', 'POST', {}) as {delivered?: number; failed?: number; note?: string};
      setStatus(res.note || (res.delivered ? 'Test webhook delivered.' : 'Test webhook failed — check the log below.'));
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not send test webhook');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); }, [token]);

  async function connectOAuth(provider: string) {
    setBusy(true);
    setStatus('');
    try {
      const res = await api(`/owner/integrations/${provider}/connect`, 'POST', {}) as {authorize_url?: string};
      if (res.authorize_url) window.location.href = res.authorize_url;
    } catch (e) {
      setStatus(e instanceof Error ? e.message : `Could not connect ${provider}`);
    } finally {
      setBusy(false);
    }
  }

  async function saveServiceM8() {
    if (!sm8Key.trim()) return;
    setBusy(true);
    setStatus('');
    try {
      await api('/owner/integrations/servicem8/key', 'POST', {api_key: sm8Key.trim()});
      setSm8Key('');
      setStatus('ServiceM8 connected.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not save ServiceM8 key');
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(provider: string) {
    setBusy(true);
    try {
      await api(`/owner/integrations/${provider}`, 'DELETE');
      setStatus(`Disconnected ${provider}.`);
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : `Could not disconnect ${provider}`);
    } finally {
      setBusy(false);
    }
  }

  async function createApiKey() {
    setBusy(true);
    setNewKey('');
    setStatus('');
    try {
      const res = await api('/owner/api-keys', 'POST', {name: keyName.trim() || 'Zapier / Make'}) as {key: string};
      setNewKey(res.key);
      setKeyName('');
      setStatus('API key created. Copy it now — it will not be shown again.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not create API key');
    } finally {
      setBusy(false);
    }
  }

  async function revokeApiKey(id: string) {
    setBusy(true);
    try {
      await api(`/owner/api-keys/${id}`, 'DELETE');
      setStatus('API key revoked.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not revoke key');
    } finally {
      setBusy(false);
    }
  }

  async function connectWhatsApp() {
    const popup = window.open('about:blank', 'concierge-wa-signup', 'width=620,height=760');
    if (!popup) {
      setStatus('Allow popups for this page to connect WhatsApp Business.');
      return;
    }
    setBusy(true);
    setStatus('');
    try {
      const start = await api('/owner/meta-messaging/whatsapp/embedded-signup/start', 'POST', {}) as {
        authorization_url: string;
        state: string;
      };
      const url = new URL(start.authorization_url);
      if (url.protocol !== 'https:' || !start.state) throw new Error('Invalid WhatsApp signup response');
      let capturedWabaId = '';
      let capturedPhoneId = '';
      let finished = false;
      const bc = typeof BroadcastChannel !== 'undefined'
        ? new BroadcastChannel('concierge-social-oauth:' + start.state)
        : null;

      const onWindowMessage = (event: MessageEvent) => {
        if (event.origin === 'https://www.facebook.com' || event.origin === 'https://web.facebook.com') {
          try {
            const payload = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
            if (payload?.type === 'WA_EMBEDDED_SIGNUP' && payload?.data) {
              if (payload.data.waba_id) capturedWabaId = String(payload.data.waba_id);
              if (payload.data.phone_number_id) capturedPhoneId = String(payload.data.phone_number_id);
            }
          } catch { /* ignore unrelated postMessage payloads */ }
          return;
        }
        if (event.origin === location.origin && event.data?.type === 'concierge-social-oauth') {
          void finish(event.data);
        }
      };

      const finish = async (data: {state?: string; code?: string; error?: string}) => {
        if (finished || !data || data.state !== start.state) return;
        finished = true;
        bc?.close();
        window.removeEventListener('message', onWindowMessage);
        try { popup.close(); } catch { /* ignore */ }
        if (data.error || !data.code) {
          setStatus('WhatsApp signup was cancelled or denied.');
          setBusy(false);
          return;
        }
        try {
          await api('/owner/meta-messaging/whatsapp/embedded-signup/complete', 'POST', {
            state: data.state,
            code: data.code,
            waba_id: capturedWabaId,
            phone_number_id: capturedPhoneId,
          });
          setStatus('WhatsApp Business connected and subscribed.');
          await load();
        } catch (e) {
          setStatus(e instanceof Error ? e.message : 'Could not complete WhatsApp signup');
        } finally {
          setBusy(false);
        }
      };

      if (bc) bc.onmessage = (event) => { void finish(event.data); };
      window.addEventListener('message', onWindowMessage);
      popup.location.href = url.href;
      setStatus('Continue in the Meta window to connect your WhatsApp Business Account.');
    } catch (e) {
      try { popup.close(); } catch { /* ignore */ }
      setStatus(e instanceof Error ? e.message : 'WhatsApp Embedded Signup is unavailable');
      setBusy(false);
    }
  }

  async function disconnectMetaChannel(id: string) {
    setBusy(true);
    setStatus('');
    try {
      await api(`/owner/meta-messaging/channels/${id}`, 'DELETE');
      setStatus('Meta messaging channel disconnected and unsubscribed.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not disconnect Meta channel');
    } finally {
      setBusy(false);
    }
  }

  async function saveTeamWebhook() {
    setBusy(true);
    setStatus('');
    try {
      const res = await api('/owner/team-chat-webhook', 'PUT', {url: teamWebhook.trim()}) as {url: string};
      setTeamWebhook(res.url || '');
      setStatus(res.url ? 'Slack / Microsoft Teams webhook saved.' : 'Slack / Microsoft Teams webhook cleared.');
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not save webhook URL');
    } finally {
      setBusy(false);
    }
  }

  return (
    <VStack gap={4} style={{padding: 16}}>
      <StatusLine text={status} />
      <Heading level={3}>Slack &amp; Microsoft Teams Alerts</Heading>
      <Card>
        <VStack gap={2} style={{padding: 16}}>
          <Text>Paste a Slack or Microsoft Teams incoming webhook HTTPS URL to receive real-time enquiry alerts.</Text>
          <HStack gap={2} style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
            <TextInput label="Slack / Teams webhook URL" value={teamWebhook} onChange={setTeamWebhook} placeholder="https://hooks.slack.com/services/..." />
            <Button label="Save webhook" variant="primary" isDisabled={busy} onClick={() => void saveTeamWebhook()} />
          </HStack>
        </VStack>
      </Card>

      <Heading level={3}>Meta Messaging (Messenger, Instagram DMs &amp; WhatsApp)</Heading>
      <Card>
        <VStack gap={3} style={{padding: 16}}>
          <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
            <HStack gap={2} style={{alignItems: 'center'}}>
              <Heading level={4}>WhatsApp Business (Embedded Signup)</Heading>
              <Badge
                label={metaOverview?.wa_embedded_signup?.enabled ? 'Available' : 'Disabled'}
                variant={metaOverview?.wa_embedded_signup?.enabled ? 'info' : 'warning'}
              />
            </HStack>
            {metaOverview?.wa_embedded_signup?.enabled ? (
              <Button label="Connect WhatsApp Business" variant="primary" isDisabled={busy} onClick={() => void connectWhatsApp()} />
            ) : null}
          </HStack>
          {metaOverview && !metaOverview.wa_embedded_signup?.enabled && metaOverview.wa_embedded_signup?.unavailable_reason ? (
            <Text>{metaOverview.wa_embedded_signup.unavailable_reason}</Text>
          ) : null}
          <Text>
            Facebook Messenger and Instagram DMs are connected automatically when you link your Facebook Page or Instagram business account in the Social tab.
          </Text>
          {metaOverview && metaOverview.channels.length > 0 ? (
            <VStack gap={2}>
              {metaOverview.channels.map((ch) => (
                <HStack key={ch.id} gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
                  <HStack gap={2} style={{alignItems: 'center'}}>
                    <Badge label={ch.channel.toUpperCase()} variant="info" />
                    <Text><strong>{ch.display_name || ch.external_id}</strong></Text>
                    <Badge label={ch.webhook_subscribed ? 'Webhook active' : 'Pending webhook'} variant={ch.webhook_subscribed ? 'success' : 'warning'} />
                  </HStack>
                  <Button label="Disconnect" variant="secondary" isDisabled={busy} onClick={() => void disconnectMetaChannel(ch.id)} />
                </HStack>
              ))}
            </VStack>
          ) : (
            <Text>No Meta messaging channels connected yet.</Text>
          )}
        </VStack>
      </Card>

      <Heading level={3}>NZ / AU Business Integrations</Heading>
      {items.map((item) => (
        <Card key={item.provider}>
          <VStack gap={2} style={{padding: 16}}>
            <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
              <HStack gap={2} style={{alignItems: 'center'}}>
                <Heading level={4}>{item.label}</Heading>
                <Badge
                  label={item.status === 'connected' ? 'Connected' : item.enabled ? 'Available' : 'Disabled'}
                  variant={item.status === 'connected' ? 'success' : item.enabled ? 'info' : 'warning'}
                />
              </HStack>
              {item.status === 'connected' ? (
                <Button label="Disconnect" variant="secondary" isDisabled={busy} onClick={() => void disconnect(item.provider)} />
              ) : item.enabled && item.method === 'oauth' ? (
                <Button label={`Connect ${item.label}`} variant="primary" isDisabled={busy} onClick={() => void connectOAuth(item.provider)} />
              ) : null}
            </HStack>
            {!item.enabled && item.unavailable_reason ? <Text>{item.unavailable_reason}</Text> : null}
            {item.last_error ? <Text>Last error: {item.last_error}</Text> : null}
            {item.provider === 'servicem8' && item.status !== 'connected' ? (
              <HStack gap={2} style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
                <TextInput label="ServiceM8 API key" value={sm8Key} onChange={setSm8Key} placeholder="Paste your ServiceM8 API key" />
                <Button label="Save key" variant="primary" isDisabled={busy} onClick={() => void saveServiceM8()} />
              </HStack>
            ) : null}
          </VStack>
        </Card>
      ))}

      <Heading level={3}>Webhook Deliveries</Heading>
      <Card>
        <VStack gap={3} style={{padding: 16}}>
          <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
            <Text>Recent signed webhook deliveries sent to your configured CRM webhook URL.</Text>
            <Button label="Send test event" variant="secondary" isDisabled={busy} onClick={() => void testWebhook()} />
          </HStack>
          {webhookEvents.length ? webhookEvents.map((ev) => (
            <HStack key={ev.id} gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', borderBottom: '1px solid var(--color-border)', paddingBottom: 6}}>
              <Text>
                <strong>{ev.event}</strong> · {ev.created_at.slice(0, 16).replace('T', ' ')}
                {ev.last_error ? ` · ${ev.last_error}` : ''}
              </Text>
              <Badge
                label={ev.delivered_at ? 'Delivered' : `Pending (${ev.attempts} tries)`}
                variant={ev.delivered_at ? 'success' : ev.last_error ? 'error' : 'warning'}
              />
            </HStack>
          )) : <Text>No webhook deliveries recorded yet.</Text>}
        </VStack>
      </Card>

      <Heading level={3}>Public REST API Keys (Zapier / Make)</Heading>
      <Card>
        <VStack gap={3} style={{padding: 16}}>
          <HStack gap={2} style={{alignItems: 'flex-end', flexWrap: 'wrap'}}>
            <TextInput label="Key name" value={keyName} onChange={setKeyName} placeholder="e.g. Zapier production" />
            <Button label="Create API key" variant="primary" isDisabled={busy} onClick={() => void createApiKey()} />
          </HStack>
          {newKey ? (
            <div style={{padding: 12, borderRadius: 8, background: 'var(--color-surface-subtle, #f6f8fa)', fontFamily: 'monospace', wordBreak: 'break-all'}}>
              {newKey}
            </div>
          ) : null}
          {keys.map((k) => (
            <HStack key={k.id} gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
              <Text><strong>{k.name || 'API key'}</strong> ({k.prefix}…) · {k.revoked ? 'Revoked' : 'Active'}</Text>
              {!k.revoked ? (
                <Button label="Revoke" variant="secondary" isDisabled={busy} onClick={() => void revokeApiKey(k.id)} />
              ) : null}
            </HStack>
          ))}
        </VStack>
      </Card>
    </VStack>
  );
}
