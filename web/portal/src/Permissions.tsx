import {useCallback, useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Badge} from '@astryxdesign/core/Badge';

/**
 * Permissions panel.
 *
 * This screen exists because the live customer tenant silently dropped every inbound
 * email: it had no owner account and no `email_read` consent, and nothing in the product
 * either showed that or offered a way to fix it. The old owner console had this; the
 * Studio portal (what customers actually see) did not.
 *
 * It shows two things: the consent toggles, and an end-to-end readiness check of the
 * whole inbound chain, so onboarding cannot call email "ready" while mail is refused.
 */

type AuthState = Record<string, {authorized?: boolean; updated_at?: string | null}>;
type Readiness = {
  ok?: boolean;
  blocked?: {check: string; message: string}[];
  warnings?: {check: string; message: string}[];
  checks?: Record<string, {ok: boolean; detail?: unknown; fix?: string}>;
  last_success_at?: string | null;
  rejected_24h?: number;
};

const CHANNELS: {key: string; label: string; help: string}[] = [
  {key: 'email_read', label: 'Read inbound email',
   help: 'Store enquiries and replies sent to your business address as drafts in your CRM.'},
  {key: 'email_send', label: 'Send email replies',
   help: 'Prepare and send replies from your business address. You still approve every message.'},
  {key: 'telephone', label: 'Answer calls',
   help: 'Let Concierge answer calls on a number you already own.'},
  {key: 'call_recording', label: 'Record calls',
   help: 'Store call recordings. Callers must be told; this is separate from answering.'},
  {key: 'sms_read', label: 'Read inbound texts',
   help: 'Store texts sent to your business number.'},
  {key: 'sms_send', label: 'Send texts',
   help: 'Send replies and reminders by text.'},
  {key: 'social', label: 'Publish to social accounts',
   help: 'Publish approved drafts to the accounts you connect.'},
];

const CHECK_LABELS: Record<string, string> = {
  api_enabled: 'Inbound email is switched on for this deployment',
  owner_account: 'A business owner login exists',
  consent: 'The owner has authorised reading email',
  reply_address: 'The business has a reply address',
  mailbox: 'The reply mailbox is enabled',
  worker_rule: 'Cloudflare routes that address to the intake Worker',
  sidecar: 'Signature checks (DKIM/DMARC) are reachable',
};

export default function Permissions({token}: {token: string}) {
  const [auth, setAuth] = useState<AuthState>({});
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [ack, setAck] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const headers = {Accept: 'application/json', ...(token ? {Authorization: 'Bearer ' + token} : {})};
    const [a, r] = await Promise.all([
      fetch('/owner/onboarding/authorizations', {headers, cache: 'no-store'}),
      fetch('/owner/onboarding/inbound-readiness', {headers, cache: 'no-store'}),
    ]);
    if (a.ok) setAuth(await a.json().catch(() => ({})));
    if (r.ok) setReadiness(await r.json().catch(() => null));
  }, [token]);

  useEffect(() => { void load(); }, [load]);

  async function toggle(channel: string, authorized: boolean) {
    if (authorized && !ack[channel]) {
      setStatus('Tick the confirmation box first — the business must approve this explicitly.');
      return;
    }
    setBusy(true);
    setStatus('');
    try {
      const response = await fetch('/owner/onboarding/authorizations', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json',
                  ...(token ? {Authorization: 'Bearer ' + token} : {})},
        body: JSON.stringify({channel, authorized, acknowledgement: authorized ? true : ack[channel] === true}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not save the permission');
      setStatus(authorized ? 'Permission granted.' : 'Permission withdrawn.');
      await load();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not save the permission');
    } finally {
      setBusy(false);
    }
  }

  const inbound = readiness?.checks || {};
  const failing = CHANNELS.filter((c) => (c.key === 'email_read' || c.key === 'email_send'));
  const other = CHANNELS.filter((c) => !(c.key === 'email_read' || c.key === 'email_send'));

  return (
    <div style={{padding: 24, display: 'flex', flexDirection: 'column', gap: 16}}>
      <Card>
        <Heading level={2}>Permissions</Heading>
        <p>
          Each capability below is an explicit instruction from the business. Granting one does not
          connect an account or start anything by itself — Trendi verifies the provider separately,
          and you can withdraw a permission at any time.
        </p>
        {status ? <p><Badge label={status} variant="info" /></p> : null}

        <Heading level={3}>Inbound email</Heading>
        <p>
          Inbound email needs both the permission below and every step of the delivery chain to be
          working. Until all of them are green, messages are refused rather than stored.
        </p>
        <div style={{display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16}}>
          {Object.entries(CHECK_LABELS).map(([key, label]) => {
            const check = inbound[key];
            const state = check ? (check.ok ? 'ok' : 'blocked') : 'unknown';
            return (
              <div key={key} style={{display: 'flex', gap: 8, alignItems: 'baseline'}}>
                <Badge label={state === 'ok' ? 'Working' : state === 'blocked' ? 'Blocked' : 'Unknown'}
                       variant={state === 'ok' ? 'success' : state === 'blocked' ? 'error' : 'warning'} />
                <span>{label}</span>
                {check && !check.ok && check.fix ? <span style={{opacity: 0.75}}>— {check.fix}</span> : null}
              </div>
            );
          })}
          {readiness?.rejected_24h ? (
            <Badge variant="warning"
                   label={readiness.rejected_24h + ' message(s) refused in the last 24 hours'} />
          ) : null}
          {readiness?.last_success_at ? (
            <span style={{opacity: 0.75}}>
              Last message stored: {new Date(readiness.last_success_at).toLocaleString()}
            </span>
          ) : (
            <span style={{opacity: 0.75}}>No inbound message has been stored for this business yet.</span>
          )}
        </div>

        {failing.map((channel) => (
          <PermissionRow key={channel.key} channel={channel} auth={auth} ack={ack} setAck={setAck}
                         busy={busy} onToggle={toggle} />
        ))}

        <Heading level={3}>Other channels</Heading>
        {other.map((channel) => (
          <PermissionRow key={channel.key} channel={channel} auth={auth} ack={ack} setAck={setAck}
                         busy={busy} onToggle={toggle} />
        ))}
      </Card>
    </div>
  );
}

function PermissionRow({channel, auth, ack, setAck, busy, onToggle}: {
  channel: {key: string; label: string; help: string};
  auth: AuthState;
  ack: Record<string, boolean>;
  setAck: (next: Record<string, boolean>) => void;
  busy: boolean;
  onToggle: (channel: string, authorized: boolean) => Promise<void>;
}) {
  const authorized = Boolean(auth[channel.key]?.authorized);
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 0',
                 borderTop: '1px solid var(--color-border)'}}>
      <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
        <Badge label={authorized ? 'Authorised' : 'Not authorised'}
               variant={authorized ? 'success' : 'warning'} />
        <strong>{channel.label}</strong>
        <span style={{marginLeft: 'auto'}}>
          <Button label={authorized ? 'Withdraw' : 'Authorise'}
                  variant={authorized ? 'secondary' : 'primary'}
                  isDisabled={busy}
                  onClick={() => void onToggle(channel.key, !authorized)} />
        </span>
      </div>
      <span style={{opacity: 0.75}}>{channel.help}</span>
      {!authorized ? (
        <label style={{display: 'flex', gap: 8, alignItems: 'center', fontSize: 14}}>
          <input type="checkbox" checked={Boolean(ack[channel.key])}
                 onChange={(e) => setAck({...ack, [channel.key]: e.target.checked})} />
          I confirm this business controls this channel and authorises Concierge to use it.
        </label>
      ) : null}
    </div>
  );
}
