/**
 * The sales pipeline board.
 *
 * Leads already carry the five stages the rest of the product uses (new, contacted, booked, won,
 * lost) and every move is written to `lead_events`. This page is the board over that engine: drag a
 * card (or use its stage menu) and the same `sales.pipeline` numbers the dashboard and the weekly
 * summary read are refreshed, so nothing can disagree about what is open or what it is worth.
 */

import {useEffect, useMemo, useState} from 'react';
import {createApi} from './api';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {StatusLine} from './StatusLine';

type Lead = {
  id: string;
  name?: string;
  company?: string;
  email?: string;
  phone?: string;
  channel: string;
  status: string;
  value_cents?: number;
  effective_value_cents?: number;
  score?: number;
  score_label?: string;
  next_action_at?: string | null;
  lost_reason?: string;
  won_at?: string | null;
  lost_at?: string | null;
  created_at?: string;
  message?: string;
};

type StageBucket = {count: number; value_cents: number; leads: Lead[]};

type Board = {
  stages: Record<string, StageBucket>;
  open_value_cents: number;
  weighted_value_cents: number;
  won_value_cents: number;
  average_lead_value_cents: number;
  odds: Record<string, number>;
};

const STAGES: {value: string; label: string}[] = [
  {value: 'new', label: 'New'},
  {value: 'contacted', label: 'Contacted'},
  {value: 'booked', label: 'Booked'},
  {value: 'won', label: 'Won'},
  {value: 'lost', label: 'Lost'},
];

const EMPTY: StageBucket = {count: 0, value_cents: 0, leads: []};

function money(cents: number) {
  return new Intl.NumberFormat('en-NZ', {
    style: 'currency',
    currency: 'NZD',
    maximumFractionDigits: 0,
  }).format((cents || 0) / 100);
}

function when(value?: string | null) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString('en-NZ', {day: 'numeric', month: 'short'});
}

function cardTitle(lead: Lead) {
  return lead.name || lead.company || lead.email || lead.phone || 'Unnamed deal';
}

function Stat({label, value, hint}: {label: string; value: string; hint?: string}) {
  return (
    <div style={{
      flex: '1 1 180px',
      minWidth: 160,
      padding: '10px 14px',
      borderRadius: 10,
      background: 'var(--color-background-surface)',
      border: '1px solid var(--color-border)',
    }}>
      <div style={{fontSize: 12, color: 'var(--color-text-secondary)'}}>{label}</div>
      <div style={{fontSize: 20, fontWeight: 650}}>{value}</div>
      {hint ? <div style={{fontSize: 12, color: 'var(--color-text-secondary)'}}>{hint}</div> : null}
    </div>
  );
}

export function Pipeline({token}: {token: string}) {
  const api = createApi(token);
  const [board, setBoard] = useState<Board | null>(null);
  const [status, setStatus] = useState('');
  const [query, setQuery] = useState('');
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [draft, setDraft] = useState({name: '', company: '', phone: '', value: ''});

  async function load() {
    try {
      setBoard(await api('/owner/crm/pipeline') as Board);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not load the pipeline');
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function move(leadId: string, to: string) {
    if (!board) return;
    const lead = Object.values(board.stages).flatMap((bucket) => bucket.leads).find((row) => row.id === leadId);
    if (!lead || lead.status === to) return;
    setStatus('Saving…');
    try {
      await api('/owner/crm/leads/' + leadId, 'PATCH', {status: to});
      await load();
      setStatus('Moved to ' + (STAGES.find((stage) => stage.value === to)?.label || to) + '.');
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not move that deal');
      await load();
    }
  }

  async function create() {
    if (!draft.name.trim() && !draft.company.trim() && !draft.phone.trim()) {
      setStatus('Add a name, company or phone first.');
      return;
    }
    setStatus('Adding…');
    try {
      await api('/owner/crm/leads', 'POST', {
        name: draft.name.trim(),
        company: draft.company.trim(),
        phone: draft.phone.trim(),
        value_cents: Math.round(Number(draft.value || 0) * 100),
      });
      setDraft({name: '', company: '', phone: '', value: ''});
      setShowNew(false);
      setStatus('Added to the board.');
      await load();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Could not add that deal');
    }
  }

  const shown = useMemo(() => {
    if (!board) return null;
    const needle = query.trim().toLowerCase();
    if (!needle) return board;
    const stages: Record<string, StageBucket> = {};
    for (const stage of STAGES) {
      const bucket = board.stages[stage.value] || EMPTY;
      const leads = bucket.leads.filter((lead) =>
        [lead.name, lead.company, lead.email, lead.phone, lead.message]
          .filter(Boolean).join(' ').toLowerCase().includes(needle));
      stages[stage.value] = {...bucket, leads, count: leads.length};
    }
    return {...board, stages};
  }, [board, query]);

  if (!board || !shown) return <p style={{padding: 24}}>Loading the sales board…</p>;

  return (
    <div>
      <p style={{fontSize: 15}}>
        Every deal in one board, by the stage it has reached. Drag a card between columns — or use the
        stage menu on it — and the pipeline, reports and weekly summary update together.
      </p>

      <div style={{display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'end', margin: '8px 0'}}>
        <div style={{flex: '1 1 240px', minWidth: 220}}>
          <TextInput label="Search deals" value={query} onChange={setQuery} />
        </div>
        <Button label={showNew ? 'Close' : 'New opportunity'} variant="primary"
                onClick={() => setShowNew(!showNew)} />
      </div>

      {showNew ? (
        <form onSubmit={(event) => {event.preventDefault(); void create();}}
              style={{display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'end', margin: '8px 0 16px'}}>
          <div style={{flex: '1 1 180px', minWidth: 160}}>
            <TextInput label="Name" value={draft.name} onChange={(value) => setDraft({...draft, name: value})} />
          </div>
          <div style={{flex: '1 1 180px', minWidth: 160}}>
            <TextInput label="Company" value={draft.company} onChange={(value) => setDraft({...draft, company: value})} />
          </div>
          <div style={{flex: '1 1 160px', minWidth: 150}}>
            <TextInput label="Phone" value={draft.phone} onChange={(value) => setDraft({...draft, phone: value})} />
          </div>
          <div style={{flex: '0 1 150px', minWidth: 120}}>
            <TextInput label="Value (NZD)" value={draft.value} onChange={(value) => setDraft({...draft, value: value})} />
          </div>
          <Button label="Add to board" variant="primary" onClick={() => void create()} />
        </form>
      ) : null}

      <div style={{display: 'flex', gap: 12, flexWrap: 'wrap', margin: '12px 0'}}>
        <Stat label="Open pipeline" value={money(board.open_value_cents)}
              hint={Object.keys(board.odds).length ? 'all open deals' : undefined} />
        <Stat label="Weighted forecast" value={money(board.weighted_value_cents)}
              hint="each stage weighted by how often it closes" />
        <Stat label="Won (last 30 days)" value={money(board.won_value_cents)} />
      </div>

      <div style={{display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 12, alignItems: 'flex-start'}}>
        {STAGES.map((stage) => {
          const bucket = shown.stages[stage.value] || EMPTY;
          const isOver = over === stage.value;
          return (
            <section
              key={stage.value}
              aria-label={stage.label + ' deals'}
              onDragOver={(event) => {event.preventDefault(); setOver(stage.value);}}
              onDragLeave={() => setOver((current) => (current === stage.value ? null : current))}
              onDrop={(event) => {
                event.preventDefault();
                const id = dragId;
                setDragId(null);
                setOver(null);
                if (id) void move(id, stage.value);
              }}
              style={{
                flex: '0 0 250px',
                minHeight: 140,
                padding: 10,
                borderRadius: 12,
                background: 'var(--color-background-surface)',
                border: isOver ? '2px dashed var(--color-accent)' : '1px solid var(--color-border)',
              }}
            >
              <header style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8}}>
                <Heading level={2} style={{fontSize: 15, margin: 0}}>{stage.label}</Heading>
                <span style={{fontSize: 12, color: 'var(--color-text-secondary)'}}>
                  {bucket.count} · {money(bucket.value_cents)}
                </span>
              </header>

              <div style={{display: 'flex', flexDirection: 'column', gap: 8}}>
                {bucket.leads.map((lead) => (
                  <article
                    key={lead.id}
                    draggable
                    onDragStart={() => setDragId(lead.id)}
                    onDragEnd={() => {setDragId(null); setOver(null);}}
                    style={{
                      background: 'var(--color-background-card)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 10,
                      padding: 10,
                      cursor: 'grab',
                      opacity: dragId === lead.id ? 0.5 : 1,
                    }}
                  >
                    <div style={{display: 'flex', justifyContent: 'space-between', gap: 8}}>
                      <strong>{cardTitle(lead)}</strong>
                      {Number(lead.value_cents || 0) ? (
                        <span style={{whiteSpace: 'nowrap'}}>{money(Number(lead.value_cents))}</span>
                      ) : null}
                    </div>
                    {lead.company && lead.name ? (
                      <div style={{fontSize: 12, color: 'var(--color-text-secondary)'}}>{lead.company}</div>
                    ) : null}
                    <div style={{display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap', alignItems: 'center'}}>
                      <Badge label={lead.channel || 'chat'} variant="neutral" />
                      {lead.channel === 'manual' ? <Badge label="offline" variant="info" /> : null}
                      {lead.score_label && lead.score_label !== 'cold' ? (
                        <Badge label={lead.score_label} variant="warning" />
                      ) : null}
                      {lead.next_action_at ? (
                        <span style={{fontSize: 12}}>Next {when(lead.next_action_at)}</span>
                      ) : null}
                      {stage.value === 'lost' && lead.lost_reason ? (
                        <span style={{fontSize: 12, color: 'var(--color-text-secondary)'}}>{lead.lost_reason}</span>
                      ) : null}
                    </div>
                    <label style={{display: 'block', marginTop: 8, fontSize: 12, color: 'var(--color-text-secondary)'}}>
                      Stage
                      <select
                        value={lead.status || stage.value}
                        aria-label={'Move ' + cardTitle(lead)}
                        onChange={(event) => void move(lead.id, event.target.value)}
                        style={{display: 'block', width: '100%', padding: 5, marginTop: 2, borderRadius: 6}}
                      >
                        {STAGES.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </label>
                  </article>
                ))}
                {!bucket.leads.length ? (
                  <p style={{fontSize: 13, opacity: 0.7, margin: 0}}>
                    {query.trim() ? 'No match here.' : 'Nothing here yet.'}
                  </p>
                ) : null}
              </div>
            </section>
          );
        })}
      </div>

      <StatusLine text={status} />
    </div>
  );
}
