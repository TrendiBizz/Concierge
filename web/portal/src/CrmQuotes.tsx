import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {Badge} from '@astryxdesign/core/Badge';
import {Table, proportional} from '@astryxdesign/core/Table';
import type {TableColumn} from '@astryxdesign/core/Table';
import {Dialog} from '@astryxdesign/core/Dialog';

type Brand = {name: string; accent: string; contact: string};
type Lead = {id: string; name?: string; email?: string; phone?: string; channel: string; status: string; created_at: string; message?: string};
type Turn = {role: string; content: string};
type QuoteLine = {description: string; quantity: number; unit_price_cents: number; amount_cents?: number};
type Quote = {id: string; title: string; currency: string; status: string; lines: QuoteLine[]; subtotal_cents: number; tax_cents: number; total_cents: number; notes?: string; created_at: string; lead_id: string; version: number; public_token?: string; sent_at?: string};
type Product = {id: string; name: string; sku?: string; unit?: string; sale_price_cents: number};

function useApi(token: string) {
  return async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {method, headers: {'Accept': 'application/json', ...(body !== undefined ? {'Content-Type': 'application/json'} : {}), Authorization: 'Bearer ' + token}, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Request failed');
    return data;
  };
}

function money(cents: number, currency: string) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency: currency || 'NZD'}).format((cents || 0) / 100);
}

export function Crm({token}: {token: string}) {
  const api = useApi(token);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [appointments, setAppointments] = useState<Record<string, unknown>[]>([]);
  const [todos, setTodos] = useState<Record<string, unknown>[]>([]);
  const [query, setQuery] = useState('');
  const [transcripts, setTranscripts] = useState<Record<string, Turn[]>>({});
  const [status, setStatus] = useState('');

  useEffect(() => {
    api('/owner/crm').then((data) => {
      setLeads((data.leads || []) as Lead[]);
      setAppointments((data.appointments || []) as Record<string, unknown>[]);
      setTodos((data.todos || []) as Record<string, unknown>[]);
    }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load enquiries'));
  }, [token]);

  async function transcript(id: string) {
    if (transcripts[id]) return;
    try {
      const turns = await api('/owner/crm/leads/' + id + '/transcript') as Turn[];
      setTranscripts({...transcripts, [id]: turns});
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Transcript unavailable'); }
  }

  const shown = leads.filter((lead) => {
    const text = [lead.name, lead.email, lead.phone, lead.message].filter(Boolean).join(' ').toLowerCase();
    return !query || text.includes(query.toLowerCase());
  });

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>CRM and enquiries</Heading>
      <p>Every enquiry from chat, email, SMS and phone lands here, with the conversation and next step.</p>
      <TextInput label="Search enquiries" value={query} onChange={setQuery} />
      <Table
        data={shown as unknown as Record<string, unknown>[]}
        idKey="id"
        density="compact"
        columns={[
          {key: 'name', header: 'Enquiry', width: proportional(1, {minWidth: 140}), renderCell: (row) => <strong>{String(row.name || row.email || row.phone || 'Enquiry')}</strong>},
          {key: 'channel', header: 'Channel', width: proportional(1, {minWidth: 90}), renderCell: (row) => String(row.channel || '')},
          {key: 'status', header: 'Status', width: proportional(1, {minWidth: 90}), renderCell: (row) => <Badge label={String(row.status || '')} variant={row.status === 'new' ? 'info' : 'neutral'} />},
          {key: 'created_at', header: 'Received', width: proportional(1, {minWidth: 150}), renderCell: (row) => new Date(String(row.created_at)).toLocaleString()},
          {key: 'id', header: '', width: proportional(1, {minWidth: 110}), renderCell: (row) => <Button label="Conversation" variant="secondary" onClick={() => transcript(String(row.id))} />},
        ] as TableColumn<Record<string, unknown>>[]}
      />
      {!shown.length ? <p>No enquiries yet. Connected channels will capture them here.</p> : null}
      {Object.entries(transcripts).map(([id, turns]) => (
        <Card key={id}>
          <Heading level={2}>Conversation</Heading>
          {turns.length ? turns.map((turn, index) => (
            <p key={index}><strong>{turn.role === 'user' ? 'Customer' : 'Concierge'}:</strong> {turn.content}</p>
          )) : <p>No saved transcript.</p>}
        </Card>
      ))}
      <div style={{display: 'flex', gap: 24, marginTop: 24, flexWrap: 'wrap'}}>
        <div><Heading level={2}>Appointments</Heading>{appointments.length ? appointments.map((a, i) => <p key={i}>{String(a.title || a.name || 'Appointment')} · {String(a.start_at || a.start || '')}</p>) : <p>None booked.</p>}</div>
        <div><Heading level={2}>Tasks</Heading>{todos.length ? todos.map((t, i) => <p key={i}>{String(t.title || 'Task')} · {String(t.status || '')}</p>) : <p>No open tasks.</p>}</div>
      </div>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


export function Quotes({token, brand}: {token: string; brand: Brand}) {
  const api = useApi(token);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [role, setRole] = useState('');
  const [leadId, setLeadId] = useState('');
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [tax, setTax] = useState(15);
  const [lines, setLines] = useState<Array<{description: string; quantity: string; price: string}>>([{description: '', quantity: '1', price: ''}]);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [pendingSignoff, setPendingSignoff] = useState<Quote | null>(null);
  const [brief, setBrief] = useState('');
  const [draftNote, setDraftNote] = useState('');

  async function load() {
    try {
      const [q, c, p, me] = await Promise.all([api('/owner/crm/quotations'), api('/owner/crm'), api('/owner/products'), api('/owner/me')]);
      setQuotes(q as Quote[]);
      setLeads(((c as {leads?: Lead[]}).leads || []) as Lead[]);
      setProducts(p as Product[]);
      setRole((me as {role: string}).role);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load quotations'); }
  }
  useEffect(() => { load(); }, [token]);

  function addProduct(id: string) {
    const product = products.find((item) => item.id === id);
    if (!product) return;
    setLines([...lines, {description: product.name, quantity: '1', price: (product.sale_price_cents / 100).toFixed(2)}]);
  }

  async function draftWithAi() {
    setBusy(true); setStatus(''); setDraftNote('');
    try {
      const result = await api('/owner/crm/quotations/draft', 'POST', {
        lead_id: leadId || null,
        brief,
        currency: 'NZD',
        tax_basis_points: Math.round(tax * 100),
      }) as {title: string; notes: string; lines: Array<{description: string; quantity: string | number; unit_price_cents: number}>; warnings?: string[]; source: string};
      setTitle(result.title);
      setNotes(result.notes || '');
      setLines(result.lines.map((line) => ({
        description: line.description,
        quantity: String(line.quantity),
        price: (line.unit_price_cents / 100).toFixed(2),
      })));
      const warning = (result.warnings || []).join(' ');
      setDraftNote(warning || (result.source === 'model'
        ? 'AI draft using your catalogue and enquiry. Check every line, price and quantity before saving.'
        : 'Drafted from the measured takeoff. Check every line before saving.'));
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not draft the quotation'); }
    setBusy(false);
  }

  async function save() {
    setBusy(true); setStatus('');
    try {
      const body = {
        lead_id: leadId, title, currency: 'NZD', tax_basis_points: Math.round(tax * 100),
        lines: lines.filter((line) => line.description.trim()).map((line) => ({
          description: line.description.trim(), quantity: line.quantity, unit_price_cents: Math.round(Number(line.price) * 100),
        })),
        notes,
      };
      await api('/owner/crm/quotations', 'POST', body);
      setStatus('Quotation saved as a draft. The owner reviews and signs it off.');
      setTitle(''); setNotes(''); setLines([{description: '', quantity: '1', price: ''}]);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the quotation'); }
    setBusy(false);
  }

  async function printQuote(id: string) {
    const response = await fetch('/owner/crm/quotations/' + id + '/print', {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) { setStatus('Could not prepare the quotation.'); return; }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  async function sendQuote(id: string) {
    setBusy(true); setStatus('');
    try {
      const result = await api('/owner/crm/quotations/' + id + '/send', 'POST') as {link: string; sent_to: string};
      setStatus('Sent to ' + result.sent_to + '. Customer link: ' + result.link);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send the quotation'); }
    setBusy(false);
  }

  async function signOff(id: string, version: number) {
    setBusy(true); setStatus('');
    try {
      await api('/owner/crm/quotations/' + id + '/status', 'POST', {status: 'reviewed', version});
      setStatus('Quotation reviewed and signed off.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Sign-off failed'); }
    setBusy(false);
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Quotations</Heading>
      <p>Build a quote from your enquiry and products. Prices are your sale prices. The business owner reviews and signs off before it is accepted.</p>
      <div style={{display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))'}}>
        <Card>
          <Heading level={2}>New quotation</Heading>
          <label style={{display: 'block', margin: '8px 0'}}>
            Enquiry
            <select value={leadId} onChange={(e) => setLeadId(e.target.value)} style={{display: 'block', width: '100%', padding: 8}}>
              <option value="">Choose an enquiry</option>
              {leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.name || lead.email || lead.phone || lead.id}</option>)}
            </select>
          </label>
          <TextInput label="Title" value={title} onChange={setTitle} />
          <TextInput label="Tax %" value={String(tax)} onChange={(v) => setTax(Number(v) || 0)} />
          <TextArea label="What is the job? (for the AI draft)" value={brief} onChange={setBrief} rows={3} />
          <Button label={busy ? 'Drafting…' : 'Draft with AI'} variant="secondary" onClick={draftWithAi} />
          {draftNote ? <p role="note"><em>{draftNote}</em></p> : null}
          <label style={{display: 'block', margin: '8px 0'}}>
            Add from product catalogue
            <select value="" onChange={(e) => addProduct(e.target.value)} style={{display: 'block', width: '100%', padding: 8}}>
              <option value="">Choose a product</option>
              {products.map((product) => <option key={product.id} value={product.id}>{product.name} — {money(product.sale_price_cents, 'NZD')}</option>)}
            </select>
          </label>
          {lines.map((line, index) => (
            <div key={index} style={{display: 'grid', gridTemplateColumns: '2fr 0.7fr 1fr', gap: 8, margin: '8px 0'}}>
              <input aria-label="Line description" placeholder="Description" value={line.description} onChange={(e) => setLines(lines.map((item, i) => i === index ? {...item, description: e.target.value} : item))} style={{padding: 8}} />
              <input aria-label="Quantity" placeholder="Qty" value={line.quantity} onChange={(e) => setLines(lines.map((item, i) => i === index ? {...item, quantity: e.target.value} : item))} style={{padding: 8}} />
              <input aria-label="Unit price" placeholder="Unit price" value={line.price} onChange={(e) => setLines(lines.map((item, i) => i === index ? {...item, price: e.target.value} : item))} style={{padding: 8}} />
            </div>
          ))}
          <Button label="Add line" variant="ghost" onClick={() => setLines([...lines, {description: '', quantity: '1', price: ''}])} />
          <TextArea label="Notes" value={notes} onChange={setNotes} rows={3} />
          <Button label={busy ? 'Saving…' : 'Save quotation'} variant="primary" onClick={save} />
        </Card>
        <Card>
          <Heading level={2}>How sign-off works</Heading>
          <p>Draft → reviewed (owner only) → accepted or declined.</p>
          <p>Concierge never sends a price without the owner's approval. Your branding: <strong>{brand.name || 'your business'}</strong>.</p>
        </Card>
      </div>
      <Heading level={2}>Your quotations</Heading>
      <Table
        data={quotes as unknown as Record<string, unknown>[]}
        idKey="id"
        density="compact"
        columns={[
          {key: 'title', header: 'Quotation', width: proportional(2, {minWidth: 180}), renderCell: (row) => <strong>{String(row.title || '')}</strong>},
          {key: 'status', header: 'Status', width: proportional(1, {minWidth: 100}), renderCell: (row) => <Badge label={String(row.status || '')} variant={row.status === 'accepted' ? 'success' : row.status === 'declined' ? 'error' : row.status === 'reviewed' ? 'info' : 'neutral'} />},
          {key: 'total_cents', header: 'Total', width: proportional(1, {minWidth: 100}), renderCell: (row) => money(Number(row.total_cents), String(row.currency || 'NZD'))},
          {key: 'id', header: 'Actions', width: proportional(1, {minWidth: 260}), renderCell: (row) => (
            <span style={{display: 'inline-flex', gap: 4, flexWrap: 'wrap'}}>
              <Button label="PDF" variant="secondary" onClick={() => printQuote(String(row.id))} />
              {row.public_token ? <Button label="Customer page" variant="ghost" onClick={() => window.open('/quote/' + row.public_token, '_blank', 'noopener')} /> : null}
              {role === 'owner' && row.status === 'draft' ? <Button label="Review" variant="primary" onClick={() => setPendingSignoff(row as unknown as Quote)} /> : null}
              {role === 'owner' && row.status === 'reviewed' ? <Button label="Send" variant="primary" onClick={() => sendQuote(String(row.id))} /> : null}
            </span>
          )},
        ] as TableColumn<Record<string, unknown>>[]}
      />
      {!quotes.length ? <p>No quotations yet.</p> : null}
      <Dialog isOpen={Boolean(pendingSignoff)} onOpenChange={(open) => { if (!open) setPendingSignoff(null); }}>
        <Heading level={2}>Sign off this quotation?</Heading>
        <p>{pendingSignoff?.title}: {pendingSignoff ? money(pendingSignoff.total_cents, pendingSignoff.currency) : ''}</p>
        <p>This marks it reviewed and ready to send. The owner is responsible for the prices and scope.</p>
        <Button label="Sign off" variant="primary" onClick={async () => { if (pendingSignoff) { await signOff(pendingSignoff.id, pendingSignoff.version); setPendingSignoff(null); } }} />
        <Button label="Cancel" variant="ghost" onClick={() => setPendingSignoff(null)} />
      </Dialog>
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}

type TimelineEvent = {channel: string; channel_label?: string; direction: string; body: string; occurred_at?: string | null};
type Contact = {case_key: string; label: string; primary_phone?: string; primary_email?: string;
  channels: string[]; event_count: number; automation_paused: boolean; last_at?: string | null};
type ContactDetail = Contact & {event_count: number; channels: string[]; events: TimelineEvent[];
  enquiries: {id: string; status: string; channel: string; message: string; created_at?: string | null}[];
  appointments: {starts_at?: string | null; status: string; name: string}[]};

export function Contacts({token}: {token: string}) {
  const api = useApi(token);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selected, setSelected] = useState<ContactDetail | null>(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [reason, setReason] = useState('');

  async function load(search: string) {
    try {
      const data = await api('/owner/contacts?limit=100&q=' + encodeURIComponent(search)) as {contacts: Contact[]};
      setContacts(data.contacts || []);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load contacts'); }
  }
  useEffect(() => { load(query); }, [token, query]);

  async function open(contact: Contact) {
    try {
      setSelected(await api('/owner/contacts/' + encodeURIComponent(contact.case_key) + '/timeline') as ContactDetail);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load that contact'); }
  }

  async function takeover(paused: boolean) {
    if (!selected) return;
    if (paused && !reason.trim()) { setStatus('Say why you are taking over before pausing the assistant.'); return; }
    try {
      await api('/owner/contacts/' + encodeURIComponent(selected.case_key) + '/takeover', 'PUT', {paused, reason});
      setStatus(paused ? 'Assistant paused for this customer.' : 'Assistant resumed.');
      await open(selected);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not change that'); }
  }

  return (
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Contacts</Heading>
      <p>
        One record per person, with every email, text, call, chat, quote and appointment in one
        thread — so a returning customer is recognised instead of appearing as a new enquiry.
      </p>
      <TextInput label="Search people" value={query} onChange={setQuery} />
      <Table
        data={contacts as unknown as Record<string, unknown>[]}
        idKey="case_key"
        density="compact"
        columns={[
          {key: 'label', header: 'Customer', width: proportional(1, {minWidth: 160}), renderCell: (row) => <strong>{String(row.label || '')}</strong>},
          {key: 'channels', header: 'Channels', width: proportional(1, {minWidth: 120}), renderCell: (row) => (Array.isArray(row.channels) ? (row.channels as string[]).join(', ') : '')},
          {key: 'event_count', header: 'Messages', width: proportional(1, {minWidth: 90}), renderCell: (row) => String(row.event_count || 0)},
          {key: 'automation_paused', header: 'Assistant', width: proportional(1, {minWidth: 110}), renderCell: (row) => <Badge label={row.automation_paused ? 'paused' : 'replying'} variant={row.automation_paused ? 'warning' : 'neutral'} />},
          {key: 'last_at', header: 'Last contact', width: proportional(1, {minWidth: 150}), renderCell: (row) => row.last_at ? new Date(String(row.last_at)).toLocaleString() : '—'},
          {key: 'case_key', header: '', width: proportional(1, {minWidth: 90}), renderCell: (row) => <Button label="Open" variant="secondary" onClick={() => open(row as unknown as Contact)} />},
        ] as TableColumn<Record<string, unknown>>[]}
      />
      {!contacts.length ? <p>No contacts yet. Each enquiry creates one, and repeat customers are merged onto it.</p> : null}

      {selected ? (
        <Card>
          <Heading level={2}>{selected.label}</Heading>
          <p>{selected.primary_phone || 'no phone'} · {selected.primary_email || 'no email'} · {selected.event_count} events across {(selected.channels || []).join(', ') || 'no channels yet'}</p>
          <label style={{display: 'block', margin: '8px 0'}}>
            Why (recorded in the customer's history)
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. rang them back myself" style={{display: 'block', padding: 8, width: '100%'}} />
          </label>
          {selected.automation_paused
            ? <Button label="Resume the assistant" variant="primary" onClick={() => takeover(false)} />
            : <Button label="Take over (pause the assistant)" variant="secondary" onClick={() => takeover(true)} />}
          <Heading level={2}>Timeline</Heading>
          {selected.events.length ? selected.events.map((event, index) => (
            <p key={index} style={{borderBottom: '1px solid var(--color-border)', paddingBottom: 6}}>
              <strong>{event.channel_label || event.channel}</strong> · {event.direction} · {(event.occurred_at || '').slice(0, 16)}
              <br />{event.body}
            </p>
          )) : <p>Nothing recorded on this contact yet.</p>}
          {selected.enquiries.length ? <><Heading level={2}>Enquiries</Heading>
            {selected.enquiries.map((enquiry) => <p key={enquiry.id}>{enquiry.channel} · {enquiry.status} · {enquiry.message}</p>)}
          </> : null}
          {selected.appointments.length ? <><Heading level={2}>Appointments</Heading>
            {selected.appointments.map((appointment, index) => <p key={index}>{appointment.name || 'Appointment'} · {appointment.status} · {(appointment.starts_at || '').slice(0, 16)}</p>)}
          </> : null}
          <Button label="Close" variant="ghost" onClick={() => setSelected(null)} />
        </Card>
      ) : null}
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}

