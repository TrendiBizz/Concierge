import {useCallback, useEffect, useState} from 'react';
import {createApi} from './api';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Switch} from '@astryxdesign/core/Switch';
import {TextArea} from '@astryxdesign/core/TextArea';
import {TextInput} from '@astryxdesign/core/TextInput';
import {StatusLine} from './StatusLine';

type Draft = {id: number; subject: string; sender: string; inbound_body: string; reply_body: string; status: string; origin?: string | null};
type Release = {label: string; summary: string; notes: string[]; unseen: boolean};

/** The small version tag in the Studio footer. Public endpoint, so it works before sign-in too. */
export function VersionLabel() {
  const [label, setLabel] = useState('');
  useEffect(() => {
    fetch('/owner/version').then((r) => r.json()).then((v) => setLabel(String(v.label || ''))).catch(() => {});
  }, []);
  return label ? <>{label} · </> : null;
}

/** "What's new": shown once per person for the newest release they have not dismissed. */
function WhatsNew({api}: {api: ReturnType<typeof createApi>}) {
  const [release, setRelease] = useState<Release | null>(null);
  useEffect(() => { api('/owner/release').then((r) => setRelease(r as Release)).catch(() => {}); }, [api]);
  if (!release?.unseen) return null;
  return (
    <Card>
      <Heading level={2}>What is new in {release.label}</Heading>
      <p>{release.summary}</p>
      <ul>{release.notes.map((note) => <li key={note}>{note}</li>)}</ul>
      <Button label="Got it" variant="primary"
        onClick={() => { void api('/owner/release/seen', 'POST').then(() => setRelease(null)).catch(() => {}); }} />
    </Card>
  );
}

/** Replies waiting for the owner. Nothing is sent to a customer until the owner approves it here. */
function NeedsYou({api}: {api: ReturnType<typeof createApi>}) {
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api('/owner/email-drafts').then((rows) => setDrafts((rows as Draft[]).filter((d) => d.status === 'draft')))
      .catch(() => setDrafts(null));
  }, [api]);
  useEffect(load, [load]);

  async function act(draft: Draft, action: 'approve' | 'discard') {
    setBusy(true); setStatus('');
    try {
      const edited = edits[draft.id];
      if (action === 'approve' && edited !== undefined && edited !== draft.reply_body) {
        await api('/owner/email-drafts/' + draft.id, 'PATCH', {reply_body: edited});
      }
      await api('/owner/email-drafts/' + draft.id + '/' + action, 'POST');
      setStatus(action === 'approve' ? 'Reply approved and queued to send.' : 'Draft discarded.');
      load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not do that'); }
    setBusy(false);
  }

  if (drafts === null) return null;
  return (
    <Card>
      <Heading level={2}>Needs you</Heading>
      {drafts.length === 0 ? <p>Nothing is waiting for you.</p> : (
        <p>{drafts.length} {drafts.length === 1 ? 'reply is' : 'replies are'} waiting for you to approve. Nothing is sent until you do.</p>
      )}
      {drafts.map((draft) => (
        <section key={draft.id} className="c-row" style={{display: 'block'}}>
          <strong>{draft.subject || 'Reply'}</strong>
          <p style={{fontSize: 13, opacity: 0.8}}>
            To {draft.sender}{draft.origin === 'concierge' ? ' · Prepared by Concierge, our assistant. Check it before you approve.' : ''}
          </p>
          <p style={{fontSize: 13, opacity: 0.8}}>They wrote: {draft.inbound_body.slice(0, 300)}</p>
          <TextArea label="Your reply" value={edits[draft.id] ?? draft.reply_body}
            onChange={(value: string) => setEdits({...edits, [draft.id]: value})} />
          <div style={{display: 'flex', gap: 8, marginTop: 8}}>
            <Button label="Approve and send" variant="primary" isDisabled={busy} onClick={() => void act(draft, 'approve')} />
            <Button label="Discard" variant="secondary" isDisabled={busy} onClick={() => void act(draft, 'discard')} />
          </div>
        </section>
      ))}
      <StatusLine text={status} />
    </Card>
  );
}

/** Read-only questions about the owner's own business. It cannot send or change anything. */
function Ask({api}: {api: ReturnType<typeof createApi>}) {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [busy, setBusy] = useState(false);
  async function ask() {
    if (!question.trim()) return;
    setBusy(true); setAnswer('Thinking…');
    try { setAnswer(((await api('/owner/ask', 'POST', {question: question.trim()})) as {answer: string}).answer); }
    catch (e) { setAnswer(e instanceof Error ? e.message : 'Could not answer that'); }
    setBusy(false);
  }
  return (
    <Card>
      <Heading level={2}>Ask Concierge</Heading>
      <p style={{fontSize: 14, opacity: 0.8}}>Ask about your business. It answers only from the information you have added, and it cannot send or change anything.</p>
      <TextInput label="Your question" value={question} onChange={setQuestion} />
      <Button label={busy ? 'Thinking…' : 'Ask'} variant="primary" isDisabled={busy} onClick={() => void ask()} />
      {answer ? <p role="status" style={{marginTop: 12}}>{answer}</p> : null}
    </Card>
  );
}

/** The 7am "what needs you today" email. Off until the owner switches it on; a quiet day sends nothing. */
function MorningEmail({api}: {api: ReturnType<typeof createApi>}) {
  const [on, setOn] = useState<boolean | null>(null);
  const [status, setStatus] = useState('');
  useEffect(() => {
    api('/owner/onboarding').then((d) => setOn(!!(d as {business?: {daily_summary?: boolean}}).business?.daily_summary)).catch(() => setOn(null));
  }, [api]);
  if (on === null) return null;
  async function change(next: boolean) {
    setStatus('');
    try { await api('/owner/onboarding/profile', 'PATCH', {daily_summary: next}); setOn(next); setStatus(next ? 'Saved. You will get a 7am email when something needs you.' : 'Saved. The 7am email is off.'); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save that'); }
  }
  return (
    <Card>
      <Heading level={2}>Morning email</Heading>
      <Switch label="Email me at 7am when something needs me" value={on} onChange={(v: boolean) => void change(v)} />
      <p style={{fontSize: 13, opacity: 0.8}}>Nothing is sent on a quiet day.</p>
      <StatusLine text={status} />
    </Card>
  );
}

export default function OwnerDesk({token}: {token: string}) {
  const api = useCallback(createApi(token), [token]);
  return (
    <div style={{display: 'grid', gap: 16, marginBottom: 20}}>
      <WhatsNew api={api} />
      <NeedsYou api={api} />
      <Ask api={api} />
      <MorningEmail api={api} />
    </div>
  );
}
