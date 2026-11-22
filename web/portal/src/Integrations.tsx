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

export function Integrations({token}: {token: string}) {
  const api = createApi(token);
  const [items, setItems] = useState<IntegrationItem[]>([]);
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [keyName, setKeyName] = useState('');
  const [newKey, setNewKey] = useState('');
  const [sm8Key, setSm8Key] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [intRes, keyRes] = await Promise.all([
        api('/owner/integrations') as Promise<{integrations: IntegrationItem[]}>,
        api('/owner/api-keys') as Promise<{keys: ApiKeyRow[]}>,
      ]);
      setItems(intRes.integrations || []);
      setKeys(keyRes.keys || []);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load integrations');
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

  return (
    <VStack gap={4} style={{padding: 16}}>
      <StatusLine text={status} />
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
