import {useEffect, useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {createApi} from './api';
import {StatusLine} from './StatusLine';

type Invoice = {
  id: string;
  number: string;
  kind: string;
  status: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  due_cents: number;
  deposit_cents: number;
  balance_cents: number;
  currency: string;
  issued_on: string;
  due_on: string | null;
  public_token: string;
};

function money(cents: number, currency: string) {
  const code = (currency || 'NZD').toUpperCase();
  const amount = ((cents || 0) / 100).toFixed(2);
  return `${code} $${amount}`;
}

type ConnectState = {
  platform_configured: boolean;
  unavailable_reason: string;
  connected: boolean;
  status?: string;
  stripe_account_id: string;
  charges_enabled: boolean;
  payouts_enabled: boolean;
};

export function Invoices({token}: {token: string}) {
  const api = createApi(token);
  const [rows, setRows] = useState<Invoice[]>([]);
  const [connect, setConnect] = useState<ConnectState | null>(null);
  const [status, setStatus] = useState('');
  const [busyId, setBusyId] = useState('');
  const [connectBusy, setConnectBusy] = useState(false);

  async function load() {
    try {
      const [data, conn] = await Promise.all([
        api('/owner/invoices') as Promise<Invoice[] | {invoices?: Invoice[]}>,
        api('/owner/payments/connect').catch(() => null) as Promise<ConnectState | null>,
      ]);
      setRows(Array.isArray(data) ? data : (data.invoices || []));
      if (conn) setConnect(conn);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load invoices');
    }
  }

  useEffect(() => { void load(); }, [token]);

  async function startStripeConnect() {
    setConnectBusy(true);
    setStatus('');
    try {
      const res = await api('/owner/payments/connect/start', 'POST', {}) as {authorize_url?: string};
      if (res.authorize_url) window.location.assign(res.authorize_url);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not start Stripe Connect onboarding');
    } finally {
      setConnectBusy(false);
    }
  }

  async function syncStripeConnect() {
    setConnectBusy(true);
    setStatus('');
    try {
      const res = await api('/owner/payments/connect/sync', 'POST', {}) as ConnectState;
      setConnect((prev) => ({...(prev || {platform_configured: true, unavailable_reason: ''}), ...res}));
      setStatus(res.charges_enabled ? 'Stripe Connect is active and ready for card payments.' : 'Stripe onboarding is still in progress.');
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not refresh Stripe Connect status');
    } finally {
      setConnectBusy(false);
    }
  }

  async function disconnectStripe() {
    if (!window.confirm('Disconnect Stripe Connect for online invoice card payments?')) return;
    setConnectBusy(true);
    setStatus('');
    try {
      await api('/owner/payments/connect/disconnect', 'POST', {});
      setStatus('Stripe Connect disconnected.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not disconnect Stripe');
    } finally {
      setConnectBusy(false);
    }
  }

  async function createCardCheckout(inv: Invoice) {
    setBusyId(inv.id);
    setStatus('');
    try {
      const kind = inv.kind === 'deposit' ? 'deposit' : inv.kind === 'balance' ? 'balance' : 'full';
      const res = await api(`/owner/invoices/${inv.id}/checkout`, 'POST', {kind}) as {checkout_url?: string};
      setStatus(res.checkout_url ? `Stripe card checkout link ready: ${res.checkout_url}` : 'Card checkout session created.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not create card checkout link');
    } finally {
      setBusyId('');
    }
  }

  async function issueBalanceInvoice(id: string) {
    setBusyId(id);
    setStatus('');
    try {
      const res = await api(`/owner/invoices/${id}/balance-invoice`, 'POST', {}) as {number?: string};
      setStatus(res.number ? `Balance invoice ${res.number} created.` : 'Balance invoice created.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not create balance invoice');
    } finally {
      setBusyId('');
    }
  }

  async function createPayLink(id: string) {
    setBusyId(id);
    setStatus('');
    try {
      const res = await api(`/owner/invoices/${id}/payment-link`, 'POST', {}) as {url?: string};
      setStatus(res.url ? `Payment link ready: ${res.url}` : 'Payment link created.');
      await load();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not create payment link');
    } finally {
      setBusyId('');
    }
  }

  return (
    <VStack gap={4} style={{padding: 16}}>
      <StatusLine text={status} />
      {connect ? (
        <Card>
          <VStack gap={2} style={{padding: 16}}>
            <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
              <HStack gap={2} style={{alignItems: 'center'}}>
                <Heading level={3}>Online Card Payments (Stripe Connect)</Heading>
                <Badge
                  label={connect.connected && connect.charges_enabled ? 'Connected' : connect.stripe_account_id ? 'Setup pending' : connect.platform_configured ? 'Available' : 'Unavailable'}
                  variant={connect.connected && connect.charges_enabled ? 'success' : connect.platform_configured ? 'info' : 'warning'}
                />
              </HStack>
              <HStack gap={2} style={{flexWrap: 'wrap'}}>
                {connect.platform_configured && (!connect.connected || !connect.charges_enabled) ? (
                  <Button
                    label={connect.stripe_account_id ? 'Continue Stripe setup' : 'Connect Stripe'}
                    variant="primary"
                    isDisabled={connectBusy}
                    onClick={() => void startStripeConnect()}
                  />
                ) : null}
                {connect.platform_configured && connect.stripe_account_id ? (
                  <Button label="Refresh status" variant="secondary" isDisabled={connectBusy} onClick={() => void syncStripeConnect()} />
                ) : null}
                {connect.connected ? (
                  <Button label="Disconnect" variant="secondary" isDisabled={connectBusy} onClick={() => void disconnectStripe()} />
                ) : null}
              </HStack>
            </HStack>
            <Text>
              {connect.connected && connect.charges_enabled
                ? 'Your Stripe Express account is connected. You can generate card checkout links directly on customer invoices (bank transfer stays available at zero fee).'
                : connect.platform_configured
                  ? 'Connect your own Stripe Express account to accept card payments directly on quotes and invoices. Bank transfer remains the zero-fee default.'
                  : connect.unavailable_reason || 'Stripe Connect is not configured on this server.'}
            </Text>
          </VStack>
        </Card>
      ) : null}
      {rows.length === 0 ? (
        <Card>
          <VStack gap={2} style={{padding: 16}}>
            <Heading level={3}>No customer invoices yet</Heading>
            <Text>When a customer accepts a quote and you issue an invoice, it appears here with its balance and public link.</Text>
          </VStack>
        </Card>
      ) : (
        rows.map((inv) => (
          <Card key={inv.id}>
            <VStack gap={2} style={{padding: 16}}>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap'}}>
                <HStack gap={2} style={{alignItems: 'center'}}>
                  <Heading level={4}>{inv.number}</Heading>
                  <Badge label={inv.status} variant={inv.status === 'paid' ? 'success' : inv.status === 'void' ? 'error' : 'info'} />
                  <Badge label={inv.kind} variant="info" />
                </HStack>
                <strong>{money(inv.total_cents, inv.currency)}</strong>
              </HStack>
              <Text>
                Issued {inv.issued_on}{inv.due_on ? ` · Due ${inv.due_on}` : ''} · Due now: {money(inv.due_cents, inv.currency)}
                {inv.balance_cents > 0 ? ` · Balance: ${money(inv.balance_cents, inv.currency)}` : ''}
              </Text>
              <HStack gap={2} style={{flexWrap: 'wrap'}}>
                {inv.public_token ? (
                  <a href={`/invoice/${inv.public_token}`} target="_blank" rel="noreferrer" className="c-btn">
                    Open customer invoice
                  </a>
                ) : null}
                {inv.status !== 'paid' && inv.status !== 'void' && connect?.connected && connect?.charges_enabled ? (
                  <Button
                    label={busyId === inv.id ? 'Creating checkout…' : 'Create card checkout link'}
                    variant="primary"
                    isDisabled={busyId === inv.id}
                    onClick={() => void createCardCheckout(inv)}
                  />
                ) : null}
                {inv.status !== 'paid' && inv.status !== 'void' ? (
                  <Button
                    label={busyId === inv.id ? 'Creating link…' : 'Create payment link'}
                    variant="secondary"
                    isDisabled={busyId === inv.id}
                    onClick={() => void createPayLink(inv.id)}
                  />
                ) : null}
                {inv.balance_cents > 0 ? (
                  <Button
                    label={busyId === inv.id ? 'Creating balance…' : 'Issue balance invoice'}
                    variant="secondary"
                    isDisabled={busyId === inv.id}
                    onClick={() => void issueBalanceInvoice(inv.id)}
                  />
                ) : null}
              </HStack>
            </VStack>
          </Card>
        ))
      )}
    </VStack>
  );
}
