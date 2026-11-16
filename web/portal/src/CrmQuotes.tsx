import {useEffect, useState} from 'react';
import {describeFailure} from './api';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Badge} from '@astryxdesign/core/Badge';
import {Table, proportional} from '@astryxdesign/core/Table';
import type {TableColumn} from '@astryxdesign/core/Table';
import {HStack} from '@astryxdesign/core/HStack';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {Timestamp} from '@astryxdesign/core/Timestamp';
import {DateTimeInput} from '@astryxdesign/core/DateTimeInput';
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {MoreMenu} from '@astryxdesign/core/MoreMenu';
import {StatusLine} from './StatusLine';

type Lead = {id: string; name?: string; email?: string; phone?: string; channel: string; status: string;
  created_at: string; message?: string; value_cents?: number; lost_reason?: string; next_action_at?: string};
type Todo = {id: number; title: string; notes?: string; due_at?: string; status: string; kind?: string; lead_id?: string};

// What the salesperson can move a deal to. These are the same five stages the API and the
// dashboard already use, in the order a job actually travels.
const STAGES: {value: string; label: string}[] = [
  {value: 'new', label: 'New'},
  {value: 'contacted', label: 'Contacted'},
  {value: 'booked', label: 'Booked'},
  {value: 'won', label: 'Won'},
  {value: 'lost', label: 'Lost'},
];
type Turn = {role: string; content: string};

function useApi(token: string) {
  return async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {method, headers: {'Accept': 'application/json', ...(body !== undefined ? {'Content-Type': 'application/json'} : {}), Authorization: 'Bearer ' + token}, body: body === undefined ? undefined : JSON.stringify(body), cache: 'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
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
  const [query, setQuery] = useState('');
  const [transcripts, setTranscripts] = useState<Record<string, Turn[]>>({});
  const [todoList, setTodoList] = useState<Todo[]>([]);
  const [newTodo, setNewTodo] = useState('');
  const [newTodoDue, setNewTodoDue] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [status, setStatus] = useState('');

  useEffect(() => {
    api('/owner/crm').then((data) => {
      setLeads((data.leads || []) as Lead[]);
      setAppointments((data.appointments || []) as Record<string, unknown>[]);
    }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load enquiries'));
    loadTodos();
  }, [token]);

  async function loadTodos() {
    try { setTodoList(await api('/owner/tasks?status=open') as Todo[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load your to-dos'); }
  }

  async function saveLead(lead: Lead, fields: Record<string, unknown>) {
    setStatus('Saving…');
    try {
      await api('/owner/crm/leads/' + lead.id, 'PATCH', fields);
      setLeads((current) => current.map((row) => row.id === lead.id ? {...row, ...fields} as Lead : row));
      setStatus('Saved. The pipeline and your dashboard use this straight away.');
      setEditing(null);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save that'); }
  }

  async function addTodo() {
    if (!newTodo.trim()) { setStatus('Say what needs doing first.'); return; }
    try {
      await api('/owner/tasks', 'POST', {title: newTodo.trim(),
        due_at: newTodoDue ? new Date(newTodoDue).toISOString() : null});
      setNewTodo(''); setNewTodoDue('');
      setStatus('Added. It is on your list until you tick it off.');
      await loadTodos();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not add that to-do'); }
  }

  async function finishTodo(todo: Todo) {
    try {
      await api('/owner/tasks/' + todo.id, 'PATCH', {status: 'done'});
      setTodoList((current) => current.filter((row) => row.id !== todo.id));
      setStatus('Done — ticked off your list.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not tick that off'); }
  }

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
    <div>
      <p style={{fontSize: 15}}>Every enquiry from chat, email, SMS and the phone lands here, with the conversation and the next step. Reply, quote or book from the same card.</p>
      <TextInput label="Search enquiries" value={query} onChange={setQuery} />
      <Table
        data={shown as unknown as Record<string, unknown>[]}
        idKey="id"
        density="compact"
        columns={[
          {key: 'name', header: 'Who', width: proportional(2, {minWidth: 150}), renderCell: (row) => (
            <VStack gap={1}>
              <strong>{String(row.name || row.email || row.phone || 'Enquiry')}</strong>
              <Timestamp value={String(row.created_at || '')} format="date_time" type="supporting" />
            </VStack>
          )},
          {key: 'channel', header: 'Came in by', width: proportional(1, {minWidth: 110}), renderCell: (row) => <Badge label={String(row.channel || 'chat')} />},
          {key: 'status', header: 'Stage', width: proportional(1, {minWidth: 150}), renderCell: (row) => (
            editing === String(row.id) ? (
              <select value={String(row.status || 'new')} aria-label="Deal stage"
                      onChange={(event) => void saveLead(row as unknown as Lead, {status: event.target.value})}
                      style={{padding: 6, borderRadius: 6}}>
                {STAGES.map((stage) => <option key={stage.value} value={stage.value}>{stage.label}</option>)}
              </select>
            ) : <Badge label={String(row.status || 'new')} variant={row.status === 'won' ? 'success' : row.status === 'lost' ? 'error' : row.status === 'new' ? 'info' : 'neutral'} />
          )},
          {key: 'value_cents', header: 'Value', width: proportional(1, {minWidth: 120}), renderCell: (row) => (
            editing === String(row.id) ? (
              <input type="number" min={0} defaultValue={Math.round(Number(row.value_cents || 0) / 100)}
                     aria-label="Deal value in dollars" style={{width: 100, padding: 6, borderRadius: 6}}
                     onBlur={(event) => {
                       const cents = Math.round(Number(event.target.value || 0) * 100);
                       if (cents !== Number(row.value_cents || 0)) void saveLead(row as unknown as Lead, {value_cents: cents});
                     }} />
            ) : (Number(row.value_cents || 0) ? money(Number(row.value_cents), 'NZD') : <span style={{opacity: 0.6}}>not set</span>)
          )},
          {key: 'next_action_at', header: 'Next step', width: proportional(1, {minWidth: 150}), renderCell: (row) => (
            editing === String(row.id) ? (
              <input type="datetime-local" aria-label="Next step due"
                     defaultValue={row.next_action_at ? String(row.next_action_at).slice(0, 16) : ''}
                     onChange={(event) => void saveLead(row as unknown as Lead, {next_action_at: event.target.value ? new Date(event.target.value).toISOString() : null})}
                     style={{padding: 6, borderRadius: 6}} />
            ) : (row.next_action_at ? <Timestamp value={String(row.next_action_at)} format="date_time" /> : <span style={{opacity: 0.6}}>none</span>)
          )},
          {key: 'id', header: '', width: proportional(1, {minWidth: 120}), renderCell: (row) => (
            <HStack gap={2} vAlign="center">
              <Button label={editing === String(row.id) ? 'Done' : 'Edit'} variant="secondary"
                      onClick={() => setEditing(editing === String(row.id) ? null : String(row.id))} />
              <MoreMenu label="More actions for this enquiry" items={[
                {label: 'Edit the deal', onClick: () => setEditing(String(row.id))},
                {label: 'Open the conversation', onClick: () => transcript(String(row.id))},
              ]} />
            </HStack>
          )},
        ] as TableColumn<Record<string, unknown>>[]}
      />
      {!shown.length ? (
        query.trim() ? (
          <div className="c-empty"><strong>No enquiries match "{query}"</strong>
            <p>Clear the search to see them all. Nothing has been deleted.</p></div>
        ) : (
          <div className="c-empty"><strong>No enquiries yet — that is normal on day one</strong><p>When someone messages the chat window, emails you or rings, the enquiry lands here with their details already filled in.</p></div>
        )
      ) : null}
      {Object.entries(transcripts).map(([id, turns]) => (
        <Card key={id}>
          <Heading level={2}>Conversation</Heading>
          {turns.length ? turns.map((turn, index) => (
            <p key={index}><strong>{turn.role === 'user' ? 'Customer' : 'Concierge'}:</strong> {turn.content}</p>
          )) : <p>No saved transcript.</p>}
        </Card>
      ))}
      <div style={{display: 'flex', gap: 24, marginTop: 24, flexWrap: 'wrap'}}>
        <div><Heading level={2}>Appointments</Heading>{appointments.length ? appointments.map((a, i) => <p key={i}>{String(a.title || a.name || 'Appointment')} · {String(a.start_at || a.start || '')}</p>) : <p style={{opacity: 0.75}}>Nothing booked yet. When a customer books from your chat window or your page, it lands here.</p>}</div>
        <div style={{flex: 1, minWidth: 320}}>
          <Heading level={2}>What needs doing</Heading>
          <HStack gap={2} vAlign="end" style={{flexWrap: 'wrap'}}>
            <TextInput label="Add a to-do" value={newTodo} onChange={setNewTodo}
                       placeholder="ring Jo back about the driveway" />
            <DateTimeInput label="Due (optional)" value={(newTodoDue || undefined) as never}
                           onChange={(value) => setNewTodoDue(String(value || ''))} />
            <Button label="Add to-do" variant="primary" onClick={() => void addTodo()} />
          </HStack>
          {todoList.length ? (
            <VStack gap={2}>
              {todoList.map((todo) => (
                <HStack key={todo.id} gap={3} vAlign="center" style={{flexWrap: 'wrap'}}>
                  <CheckboxInput label={todo.title || 'To-do'} value={false}
                                 onChange={() => void finishTodo(todo)} />
                  {todo.due_at ? <Timestamp value={todo.due_at} format="date_time" type="supporting" /> : null}
                </HStack>
              ))}
            </VStack>
          ) : <p style={{opacity: 0.75}}>Nothing waiting on you. A follow-up appears here automatically when an enquiry goes quiet.</p>}
        </div>
      </div>
      {<StatusLine text={status} />}
    </div>
  );
}


type TimelineEvent = {channel: string; channel_label?: string; direction: string; body: string; occurred_at?: string | null};
type Contact = {case_key: string; label: string; company?: string; primary_phone?: string; primary_email?: string;
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
  const [addresses, setAddresses] = useState<{id: number; kind: string; value: string; label: string; source: string}[]>([]);
  const [newKind, setNewKind] = useState('phone');
  const [newValue, setNewValue] = useState('');
  const [team, setTeam] = useState<{id: string; email: string}[]>([]);
  const [companyList, setCompanyList] = useState<{id: string; name: string}[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [bulkOwner, setBulkOwner] = useState('');

  async function load(search: string) {
    try {
      const data = await api('/owner/contacts?limit=100&q=' + encodeURIComponent(search)) as {contacts: Contact[]};
      setContacts(data.contacts || []);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load contacts'); }
  }
  useEffect(() => { load(query); }, [token, query]);
  useEffect(() => {
    api('/owner/team').then((data) => setTeam(((data as {members?: {id: string; email: string}[]}).members || [])))
      .catch(() => setTeam([]));
    api('/owner/companies').then((data) => setCompanyList(data as {id: string; name: string}[]))
      .catch(() => setCompanyList([]));
  }, [token]);

  async function setAssignee(userId: string) {
    if (!selected) return;
    try {
      await api('/owner/contacts/' + encodeURIComponent(selected.case_key) + '/assignee', 'PUT',
                {user_id: userId || null});
      // Keep the card in step with what was just saved: reloading the list alone left the
      // picker showing "Nobody yet" straight after assigning someone.
      setSelected({...selected, assigned_to: userId || undefined} as ContactDetail);
      setStatus(userId ? 'Saved. That person now owns this account.' : 'Saved. Nobody owns this account now.');
      await load(query);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the owner'); }
  }

  async function bulkAssign() {
    if (!picked.length) { setStatus('Tick the people you want to assign first.'); return; }
    try {
      const result = await api('/owner/contacts/bulk-assign', 'POST',
                                {case_keys: picked, user_id: bulkOwner || null}) as {updated: number};
      setStatus('Assigned ' + result.updated + ' ' + (result.updated === 1 ? 'person' : 'people') + '.');
      setPicked([]);
      await load(query);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not assign those people'); }
  }

  async function setCompany(companyId: string) {
    if (!selected) return;
    try {
      await api('/owner/contacts/' + encodeURIComponent(selected.case_key) + '/company', 'PUT',
                {company_id: companyId || null});
      setSelected({...selected, company_id: companyId || undefined} as ContactDetail);
      setStatus(companyId ? 'Saved. They are now part of that company.' : 'Saved. They are not in a company now.');
      await load(query);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the company'); }
  }

  async function open(contact: Contact) {
    try {
      setSelected(await api('/owner/contacts/' + encodeURIComponent(contact.case_key) + '/timeline') as ContactDetail);
      await loadAddresses(contact.case_key);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load that contact'); }
  }

  async function loadAddresses(caseKey: string) {
    try {
      const data = await api('/owner/contacts/' + encodeURIComponent(caseKey) + '/addresses') as {addresses: {id: number; kind: string; value: string; label: string; source: string}[]};
      setAddresses(data.addresses || []);
    } catch { setAddresses([]); }
  }

  async function addAddress() {
    if (!selected) return;
    if (!newValue.trim()) { setStatus('Enter the phone number or email address to add.'); return; }
    try {
      await api('/owner/contacts/' + encodeURIComponent(selected.case_key) + '/addresses', 'POST', {kind: newKind, value: newValue.trim()});
      setNewValue(''); setStatus('Added. Anything from that address now lands on this customer.');
      await loadAddresses(selected.case_key);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not add that address'); }
  }

  async function removeAddress(id: number) {
    if (!selected) return;
    try {
      await api('/owner/contacts/' + encodeURIComponent(selected.case_key) + '/addresses/' + id, 'DELETE');
      setStatus('Address removed.');
      await loadAddresses(selected.case_key);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not remove that address'); }
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
    <div>
      <p>
        One record per person, with every email, text, call, chat, quote and appointment in one
        thread — so a returning customer is recognised instead of appearing as a new enquiry.
      </p>
      <TextInput label="Search people" value={query} onChange={setQuery} />
      <HStack gap={3} vAlign="end" style={{flexWrap: 'wrap'}}>
        <Text size="sm" color="secondary">
          {picked.length ? picked.length + ' selected' : 'Tick people to assign them in one go'}
        </Text>
        <label style={{display: 'block'}}>
          Assign to
          <select aria-label="Assign selected to" value={bulkOwner}
                  onChange={(event) => setBulkOwner(event.target.value)}
                  style={{display: 'block', padding: 8, borderRadius: 6, minWidth: 220}}>
            <option value="">Nobody (clear owner)</option>
            {team.map((person) => <option key={person.id} value={person.id}>{person.email}</option>)}
          </select>
        </label>
        <Button label="Assign selected" variant="primary" isDisabled={!picked.length}
                onClick={() => void bulkAssign()} />
      </HStack>
      <Table
        data={contacts as unknown as Record<string, unknown>[]}
        idKey="case_key"
        density="compact"
        columns={[
          {key: 'pick', header: '', width: proportional(1, {minWidth: 60}), renderCell: (row) => (
            <CheckboxInput label={'Select ' + String(row.label || 'this person')}
                           isLabelHidden value={picked.includes(String(row.case_key))}
                           onChange={() => setPicked((current) => current.includes(String(row.case_key))
                             ? current.filter((key) => key !== String(row.case_key))
                             : [...current, String(row.case_key)])} />
          )},
          {key: 'label', header: 'Customer', width: proportional(2, {minWidth: 170}), renderCell: (row) => (
            <VStack gap={1}>
              <span><strong>{String(row.label || '')}</strong>{row.company ? <span style={{opacity: 0.75}}> · {String(row.company)}</span> : null}</span>
              <span>
                <Badge label={row.automation_paused ? 'assistant paused' : 'assistant replying'}
                       variant={row.automation_paused ? 'warning' : 'neutral'} />
              </span>
            </VStack>
          )},
          {key: 'channels', header: 'Reach', width: proportional(1, {minWidth: 130}), renderCell: (row) => (
            <span>
              {Array.isArray(row.channels) ? (row.channels as string[]).join(', ') : 'none'}
              <span style={{opacity: 0.65}}> · {String(row.event_count || 0)} messages</span>
            </span>
          )},
          {key: 'assignee_email', header: 'Owner', width: proportional(1, {minWidth: 140}),
           renderCell: (row) => row.assignee_email ? String(row.assignee_email) : <span style={{opacity: 0.6}}>nobody</span>},
          {key: 'last_at', header: 'Last contact', width: proportional(1, {minWidth: 150}), renderCell: (row) => row.last_at ? new Date(String(row.last_at)).toLocaleString() : '—'},
          {key: 'case_key', header: '', width: proportional(1, {minWidth: 90}), renderCell: (row) => <Button label="Open" variant="secondary" onClick={() => open(row as unknown as Contact)} />},
        ] as TableColumn<Record<string, unknown>>[]}
      />
      {!contacts.length ? (
        query.trim() ? (
          <div className="c-empty"><strong>No contacts match "{query}"</strong>
            <p>Clear the search box above to see everyone.</p></div>
        ) : (
          <div className="c-empty"><strong>No contacts yet</strong><p>Every enquiry creates one automatically, and a repeat customer is merged onto the same card instead of appearing twice.</p></div>
        )
      ) : null}

      {selected ? (
        <Card>
          <Heading level={2}>{selected.label}{selected.company ? ' · ' + selected.company : ''}</Heading>
          <p>{selected.primary_phone || 'no phone'} · {selected.primary_email || 'no email'} · {selected.event_count} events across {(selected.channels || []).join(', ') || 'no channels yet'}</p>
          <HStack gap={3} vAlign="end" style={{flexWrap: 'wrap', margin: '8px 0'}}>
            <label style={{display: 'block'}}>
              Who owns this account
              <select aria-label="Account owner" value={(selected as unknown as {assigned_to?: string}).assigned_to || ''}
                      onChange={(event) => void setAssignee(event.target.value)}
                      style={{display: 'block', padding: 8, borderRadius: 6, minWidth: 220}}>
                <option value="">Nobody yet</option>
                {team.map((person) => <option key={person.id} value={person.id}>{person.email}</option>)}
              </select>
            </label>
            <label style={{display: 'block'}}>
              Company
              <select aria-label="Company" value={(selected as unknown as {company_id?: string}).company_id || ''}
                      onChange={(event) => void setCompany(event.target.value)}
                      style={{display: 'block', padding: 8, borderRadius: 6, minWidth: 220}}>
                <option value="">No company</option>
                {companyList.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
              </select>
            </label>
          </HStack>
          <label style={{display: 'block', margin: '8px 0'}}>
            Why (recorded in the customer's history)
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. rang them back myself" style={{display: 'block', padding: 8, width: '100%'}} />
          </label>
          {selected.automation_paused
            ? <Button label="Resume the assistant" variant="primary" onClick={() => takeover(false)} />
            : <Button label="Take over (pause the assistant)" variant="secondary" onClick={() => takeover(true)} />}
          <Heading level={2}>Also reachable at</Heading>
          <p style={{fontSize: 14}}>Every phone number and email that belongs to this person. Anything arriving from one of these is treated as the same customer, not a stranger.</p>
          {addresses.map((address) => (
            <div key={address.id} style={{display: 'flex', gap: 12, alignItems: 'center', borderBottom: '1px solid var(--color-border)', padding: '6px 0'}}>
              <span style={{flex: 1}}>
                {address.kind === 'phone' ? 'phone' : 'email'} · <strong>{address.value}</strong>
                {' · '}
                <span style={{opacity: 0.75}}>{
                  {phone: 'captured from a call', voice: 'captured from a call',
                   email: 'captured from an email', sms: 'captured from a text',
                   chat: 'given in a chat', owner: 'added by you',
                   import: 'from your import', backfill: 'from your existing records',
                   inbound: 'captured automatically'}[address.source] || address.source
                }</span>
              </span>
              <Button label="Remove" variant="ghost" onClick={() => removeAddress(address.id)} />
            </div>
          ))}
          {!addresses.length ? <p>No addresses recorded yet.</p> : null}
          <div style={{display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 8}}>
            <label>
              Kind
              <select value={newKind} onChange={(e) => setNewKind(e.target.value)} style={{display: 'block', padding: 8}}>
                <option value="phone">phone</option>
                <option value="email">email</option>
              </select>
            </label>
            <div style={{flex: 1, minWidth: 220}}>
              <TextInput label="Another phone or email" value={newValue} onChange={setNewValue} />
            </div>
            <Button label="Add address" variant="secondary" onClick={addAddress} />
          </div>
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
      {<StatusLine text={status} />}
    </div>
  );
}

export {Quotes} from './Quotes';
