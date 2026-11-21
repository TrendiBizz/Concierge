import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {createApi as useApi} from './api';
import {StatusLine} from './StatusLine';

type Req = {id: string; email: string; kind: string; note: string; status: string;
            created_at: string; handled_at: string | null};
type Consent = {channel: string; granted: boolean; source: string; recorded_at: string};

/** Whole working days (Mon–Fri) between two dates; the Privacy Act clock is 20 of them. */
export function workingDaysSince(from: Date, now: Date = new Date()): number {
  let days = 0;
  const cursor = new Date(from);
  cursor.setHours(0, 0, 0, 0);
  const end = new Date(now);
  end.setHours(0, 0, 0, 0);
  while (cursor < end) {
    cursor.setDate(cursor.getDate() + 1);
    const day = cursor.getDay();
    if (day !== 0 && day !== 6) days += 1;
  }
  return days;
}

/**
 * Privacy requests and consent.
 *
 * When a customer asks for their details at /privacy, the owner is emailed "see it in Studio".
 * Until this screen existed there was nothing in Studio to see, and the 20-working-day limit in the
 * Privacy Act 2020 ran out unnoticed.
 */
export function Privacy({token}: {token: string}) {
  const api = useApi(token);
  const [requests, setRequests] = useState<Req[]>([]);
  const [status, setStatus] = useState('');
  const [confirming, setConfirming] = useState('');
  const [contact, setContact] = useState('');
  const [consents, setConsents] = useState<Consent[]>([]);

  async function load() {
    try { setRequests(await api('/owner/privacy/requests') as Req[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load privacy requests'); }
  }
  useEffect(() => { void load(); }, [token]);

  async function erase(request: Req) {
    try {
      const result = await api('/owner/privacy/requests/' + request.id + '/erase', 'POST') as {erased_leads: number};
      setConfirming('');
      setStatus('Done. Removed ' + request.email + ' from ' + result.erased_leads + ' enquiries.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not erase that person'); }
  }

  async function lookup() {
    const key = contact.trim().toLowerCase();
    if (!key) return;
    try { setConsents(await api('/owner/privacy/contacts/' + encodeURIComponent(key) + '/consent') as Consent[]); setStatus(''); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load consent'); }
  }

  async function record(channel: string, granted: boolean) {
    const key = contact.trim().toLowerCase();
    if (!key) { setStatus('Enter the customer\'s email or phone first.'); return; }
    try {
      await api('/owner/privacy/contacts/' + encodeURIComponent(key) + '/consent', 'POST',
                {channel, granted, source: 'Studio'});
      setStatus('Saved. ' + (granted ? 'Agreed to' : 'Declined') + ' contact by ' + channel + '.');
      await lookup();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save consent'); }
  }

  return (
    <VStack gap={3}>
      <Card>
        <Heading level={2}>Privacy requests</Heading>
        <Text size="sm" color="secondary">
          A customer can ask what you hold on them, or ask you to delete it. You must answer within
          20 working days. “Erase” removes their details from enquiries, messages, bookings and
          quotes and keeps your totals.
        </Text>
        {requests.length ? (
          <VStack gap={2}>
            {requests.map((request) => {
              const open = request.status !== 'done';
              const age = workingDaysSince(new Date(request.created_at));
              const late = open && age > 20;
              return (
                <VStack key={request.id} gap={1}>
                  <HStack gap={3} vAlign="center" style={{flexWrap: 'wrap'}}>
                    <strong>{request.email}</strong>
                    <Text size="sm" color="secondary">
                      {request.kind === 'delete' ? 'Delete my details' : 'Show me my details'}
                      {' · '}{new Date(request.created_at).toLocaleDateString()}
                      {open ? ' · ' + age + ' of 20 working days used' : ' · done'}
                    </Text>
                    {late ? <strong>Overdue</strong> : null}
                    {open && request.kind === 'delete' && confirming !== request.id
                      ? <Button label="Erase" variant="secondary" onClick={() => setConfirming(request.id)} /> : null}
                    {confirming === request.id ? (
                      <>
                        <Text size="sm">This cannot be undone.</Text>
                        <Button label="Yes, erase" variant="primary" onClick={() => void erase(request)} />
                        <Button label="Cancel" variant="ghost" onClick={() => setConfirming('')} />
                      </>
                    ) : null}
                  </HStack>
                  {request.note ? <Text size="sm" color="secondary">{request.note}</Text> : null}
                </VStack>
              );
            })}
          </VStack>
        ) : <Text size="sm" color="secondary">No requests.</Text>}
      </Card>
      <Card>
        <Heading level={2}>Who agreed to be contacted</Heading>
        <Text size="sm" color="secondary">Record whether a customer agreed to hear from you on a channel.</Text>
        <TextInput label="Customer email or phone" value={contact} onChange={setContact} />
        <HStack gap={2} style={{flexWrap: 'wrap'}}>
          <Button label="Show" variant="secondary" onClick={() => void lookup()} />
          {['email', 'sms', 'voice'].map((channel) => (
            <span key={channel}>
              <Button label={'Agreed: ' + channel} variant="ghost" onClick={() => void record(channel, true)} />
              <Button label={'Declined: ' + channel} variant="ghost" onClick={() => void record(channel, false)} />
            </span>
          ))}
        </HStack>
        {consents.map((c, i) => (
          <Text key={i} size="sm">{c.channel}: {c.granted ? 'agreed' : 'declined'} ({new Date(c.recorded_at).toLocaleDateString()})</Text>
        ))}
        <StatusLine text={status} />
      </Card>
    </VStack>
  );
}
