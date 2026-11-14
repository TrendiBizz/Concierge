import {useEffect, useRef, useState} from 'react';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {Heading} from '@astryxdesign/core/Heading';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {Timestamp} from '@astryxdesign/core/Timestamp';
import {ChatLayout, ChatMessageList, ChatMessage, ChatMessageBubble, ChatMessageMetadata,
  ChatComposer, ChatSystemMessage} from '@astryxdesign/core/Chat';
import {createApi} from './api';
import {StatusLine} from './StatusLine';

type Phone = {transport: string; paired: boolean; online: boolean; last_seen: string | null; receive_verified: boolean | null};
type Conversation = {id: string; phone: string; name: string; lead_id: string | null; last_text: string;
  last_author: 'customer' | 'ai' | 'owner'; last_at: string; message_count: number; paused: boolean};
type Message = {id: number; author: 'customer' | 'ai' | 'owner'; text: string; at: string};
type Thread = {id: string; phone: string; paused: boolean; opted_out: boolean; messages: Message[]};

const AUTHOR_LABEL = {customer: 'Customer', ai: 'Concierge (AI)', owner: 'You'} as const;

/**
 * Text conversations, one per customer, with the assistant's and the owner's replies told apart.
 *
 * Built from Astryx's Chat components. "Take over" stops the assistant replying to that person on
 * every channel (the same switch as on an enquiry); replying takes over automatically; "Hand back"
 * lets the assistant answer again. Replies go out through the business's own texting route,
 * including the paired phone, so the customer sees the same number either way.
 */
export function Texts({token}: {token: string}) {
  const api = createApi(token);
  const [phone, setPhone] = useState<Phone | null>(null);
  const [list, setList] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [thread, setThread] = useState<Thread | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const selectedRef = useRef('');
  selectedRef.current = selected;

  async function loadInbox() {
    try {
      const data = await api('/owner/sms/inbox') as {phone: Phone; conversations: Conversation[]};
      setPhone(data.phone); setList(data.conversations);
      if (!selectedRef.current && data.conversations.length) setSelected(data.conversations[0].id);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load your texts'); }
  }
  async function loadThread(id: string) {
    if (!id) { setThread(null); return; }
    try { setThread(await api('/owner/sms/conversations/' + id) as Thread); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load that conversation'); }
  }
  useEffect(() => {
    loadInbox();
    const timer = window.setInterval(() => { loadInbox(); if (selectedRef.current) loadThread(selectedRef.current); }, 15000);
    return () => window.clearInterval(timer);
  }, [token]);
  useEffect(() => { loadThread(selected); }, [selected]);

  async function setTakeover(paused: boolean) {
    if (!thread) return;
    setBusy(true);
    try {
      await api('/owner/sms/conversations/' + thread.id + '/takeover', 'POST', {paused});
      setStatus(paused ? 'You have taken over. Concierge will not reply to this person until you hand back.'
                       : 'Handed back. Concierge will answer this person again.');
      await Promise.all([loadThread(thread.id), loadInbox()]);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not change who is replying'); }
    finally { setBusy(false); }
  }

  async function send(value: string) {
    const text = value.trim();
    if (!thread || !text) return;
    setBusy(true);
    try {
      const result = await api('/owner/sms/conversations/' + thread.id + '/reply', 'POST',
        {text, request_id: crypto.randomUUID()}) as {status: string};
      setDraft('');
      setStatus(result.status === 'queued' ? 'Sent to your phone to text out. It goes within a few seconds while the phone link is on.'
                                           : 'Sent.');
      await Promise.all([loadThread(thread.id), loadInbox()]);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send that text'); }
    finally { setBusy(false); }
  }

  const offline = phone && phone.transport === 'device' && phone.paired && !phone.online;
  const who = (c: {name?: string; phone: string}) => c.name || c.phone || 'Unknown number';

  return (
    <VStack gap={4} style={{padding: 16}}>
      {phone ? (
        <HStack gap={2} style={{alignItems: 'center', flexWrap: 'wrap'}}>
          <Badge label={phone.transport === 'device' ? (phone.paired ? (phone.online ? 'Phone link online' : 'Phone offline') : 'No phone paired')
                        : 'Texting: ' + phone.transport}
                 variant={offline || (phone.transport === 'device' && !phone.paired) ? 'error' : 'success'} />
          {phone.last_seen ? <Text>Last heard from <Timestamp value={phone.last_seen} /></Text> : null}
          {phone.receive_verified === false ? <Badge label="No text received yet" variant="warning" /> : null}
        </HStack>
      ) : null}
      {offline ? <StatusLine tone="warning" text="Your phone link is offline, so new texts are not reaching Concierge and replies wait. Open the Mac and check the Trendi Phone Connector is running." /> : null}
      <StatusLine text={status} />
      <div style={{display: 'grid', gridTemplateColumns: 'minmax(220px, 320px) 1fr', gap: 16, minHeight: 520}}>
        <VStack gap={1} role="list" aria-label="Text conversations" style={{overflowY: 'auto', maxHeight: 640}}>
          {list.length === 0 ? <Text>No text conversations yet. When a customer texts your business number, it shows here.</Text> : null}
          {list.map((c) => (
            <button key={c.id} type="button" role="listitem" className="c-nav-item" data-active={c.id === selected}
                    aria-current={c.id === selected ? 'true' : undefined} onClick={() => setSelected(c.id)}
                    style={{textAlign: 'left', padding: 10, borderRadius: 8, display: 'block', width: '100%'}}>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center'}}>
                <strong>{who(c)}</strong>
                {c.paused ? <Badge label="You" variant="purple" /> : <Badge label="AI" variant="info" />}
              </HStack>
              <div style={{opacity: .75, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
                {AUTHOR_LABEL[c.last_author]}: {c.last_text}
              </div>
              <div style={{opacity: .6, fontSize: 12}}><Timestamp value={c.last_at} /></div>
            </button>
          ))}
        </VStack>
        <div style={{display: 'flex', flexDirection: 'column', minHeight: 520}}>
          {thread ? (
            <>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', paddingBottom: 8, flexWrap: 'wrap'}}>
                <Heading level={3}>{who(list.find((c) => c.id === thread.id) || thread)}</Heading>
                {thread.paused
                  ? <Button label="Hand back to Concierge" variant="secondary" isDisabled={busy} onClick={() => setTakeover(false)} />
                  : <Button label="Take over" variant="primary" isDisabled={busy} onClick={() => setTakeover(true)} />}
              </HStack>
              <div style={{flex: 1, minHeight: 420}}>
                <ChatLayout
                  composer={thread.opted_out
                    ? <ChatSystemMessage>This person replied STOP, so they cannot be texted.</ChatSystemMessage>
                    : <ChatComposer value={draft} onChange={setDraft} onSubmit={send} isDisabled={busy}
                                    placeholder={thread.paused ? 'Text this customer yourself' : 'Type to reply yourself (this takes over from Concierge)'} />}>
                  <ChatMessageList emptyState={<Text>No messages yet.</Text>}>
                    {thread.paused ? <ChatSystemMessage variant="divider">You are replying. Concierge is paused for this person.</ChatSystemMessage> : null}
                    {thread.messages.map((m) => (
                      <ChatMessage key={m.id} sender={m.author === 'customer' ? 'user' : 'assistant'}
                                   name={AUTHOR_LABEL[m.author]}
                                   metadata={<ChatMessageMetadata timestamp={<Timestamp value={m.at} />} />}>
                        <ChatMessageBubble variant={m.author === 'ai' ? 'ghost' : 'filled'}>{m.text}</ChatMessageBubble>
                      </ChatMessage>
                    ))}
                  </ChatMessageList>
                </ChatLayout>
              </div>
            </>
          ) : <Text>Pick a conversation.</Text>}
        </div>
      </div>
    </VStack>
  );
}

export default Texts;
