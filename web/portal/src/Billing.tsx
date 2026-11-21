import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {createApi as useApi} from './api';
import {StatusLine} from './StatusLine';

type BillingState = {status: string; grace_until: string | null; renews_on: string | null;
                     cancels_at_period_end: boolean; paused_for_billing: boolean; portal_available: boolean};
type Invoice = {id: string; number: string; plan: string; amount_cents: number; currency: string;
                status: string; issued_on: string; public_token: string};

/** One plain sentence about where the subscription stands. */
export function describeBilling(state: BillingState): string {
  const date = (value: string | null) => (value ? new Date(value).toLocaleDateString() : '');
  if (state.paused_for_billing) return 'Concierge is paused because the subscription is not paid. Update your card to resume it straight away; enquiries are still being captured.';
  switch (state.status) {
    case 'past_due': return 'Your last payment did not go through. Concierge keeps working until ' + (date(state.grace_until) || 'the grace period ends') + '. Update your card before then.';
    case 'canceled': return 'This subscription has ended.';
    case 'unpaid': return 'The subscription is unpaid.';
    case 'trialing': return 'You are on a trial' + (state.renews_on ? ' until ' + date(state.renews_on) : '') + '.';
    case 'active':
      if (state.cancels_at_period_end) return 'Your subscription is cancelled and runs until ' + (date(state.renews_on) || 'the end of this period') + '.';
      return 'Your subscription is active' + (state.renews_on ? ' and renews on ' + date(state.renews_on) : '') + '.';
    default: return 'This business is not on a card subscription (for example it is paid by bank transfer).';
  }
}

/** Billing and invoices: where the subscription stands, the Stripe portal, and every tax invoice. */
export function Billing({token}: {token: string}) {
  const api = useApi(token);
  const [state, setState] = useState<BillingState | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [status, setStatus] = useState('');

  useEffect(() => {
    (async () => {
      try {
        setState(await api('/owner/billing/status') as BillingState);
        setInvoices(await api('/owner/billing/invoices') as Invoice[]);
      } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load billing'); }
    })();
  }, [token]);

  async function openPortal() {
    try {
      const {url} = await api('/owner/billing/portal', 'POST') as {url: string};
      window.location.assign(url);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not open the billing portal'); }
  }

  return (
    <VStack gap={3}>
      <Card>
        <Heading level={2}>Your subscription</Heading>
        {state ? <Text size="sm">{describeBilling(state)}</Text> : <Text size="sm" color="secondary">Loading…</Text>}
        {state?.portal_available
          ? <Button label="Update card, change plan or cancel" variant="primary" onClick={() => void openPortal()} />
          : <Text size="sm" color="secondary">To change your card or plan, email us and we will do it for you.</Text>}
      </Card>
      <Card>
        <Heading level={2}>Invoices</Heading>
        {invoices.length ? (
          <VStack gap={1}>
            {invoices.map((invoice) => (
              <HStack key={invoice.id} gap={3} vAlign="center" style={{flexWrap: 'wrap'}}>
                <strong>{invoice.number}</strong>
                <Text size="sm" color="secondary">
                  {new Date(invoice.issued_on).toLocaleDateString()} · {(invoice.amount_cents / 100).toFixed(2)} {invoice.currency} · {invoice.status}
                </Text>
                <a href={'/receipt/' + invoice.public_token} target="_blank" rel="noreferrer">View</a>
              </HStack>
            ))}
          </VStack>
        ) : <Text size="sm" color="secondary">No invoices yet.</Text>}
        <StatusLine text={status} />
      </Card>
    </VStack>
  );
}
