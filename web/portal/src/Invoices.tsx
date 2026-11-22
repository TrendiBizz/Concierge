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

export function Invoices({token}: {token: string}) {
  const api = createApi(token);
  const [rows, setRows] = useState<Invoice[]>([]);
  const [status, setStatus] = useState('');
  const [busyId, setBusyId] = useState('');

  async function load() {
    try {
      const data = await api('/owner/invoices') as Invoice[] | {invoices?: Invoice[]};
      setRows(Array.isArray(data) ? data : (data.invoices || []));
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load invoices');
    }
  }

  useEffect(() => { void load(); }, [token]);

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
                {inv.status !== 'paid' && inv.status !== 'void' ? (
                  <Button
                    label={busyId === inv.id ? 'Creating link…' : 'Create payment link'}
                    variant="secondary"
                    isDisabled={busyId === inv.id}
                    onClick={() => void createPayLink(inv.id)}
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
