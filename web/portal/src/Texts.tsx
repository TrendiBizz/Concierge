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

type Channel = 'all' | 'sms' | 'chat' | 'email' | 'phone' | 'messenger' | 'instagram' | 'whatsapp';
type MetaChannel = 'whatsapp' | 'messenger' | 'instagram';
type Phone = {transport: string; paired: boolean; online: boolean; last_seen: string | null; receive_verified: boolean | null};
type Conversation = {id: string; phone: string; name: string; lead_id: string | null; last_text: string;
  last_author: 'customer' | 'ai' | 'owner'; last_at: string; message_count: number; paused: boolean};
type Message = {id: number; author: 'customer' | 'ai' | 'owner'; text: string; at: string};
type Thread = {id: string; phone: string; paused: boolean; opted_out: boolean; messages: Message[]};

type MetaConversation = {
  channel: MetaChannel;
  sender_id: string;
  sender_name: string;
  channel_external_id: string;
  last_text: string;
  last_direction: 'in' | 'out';
  last_at: string;
  last_inbound_at: string | null;
  window_open: boolean;
  window_expires_at: string | null;
  message_count: number;
};

type MetaMessage = {
  id: string;
  direction: 'in' | 'out';
  text: string;
  template_name?: string;
  created_at: string;
};

type MetaThread = {
  channel: MetaChannel;
  sender_id: string;
  sender_name: string;
  channel_external_id: string;
  window_open: boolean;
  window_expires_at: string | null;
  messages: MetaMessage[];
};

type WaTemplate = {
  name: string;
  language: string;
  category: string;
};

type EmailDraft = {
  id: number;
  sender: string;
  subject: string;
  inbound_body: string;
  reply_body: string;
  status: string;
  created_at: string;
};

type PhoneCall = {
  call_sid: string;
  from_number: string;
  status: string;
  duration_seconds: number | null;
  started_at: string;
  session_id?: string | null;
  summary?: string | null;
};

type Recording = {
  session_id: string;
  conversation_id: string;
  mime_type: string;
  created_at: string;
};

type UnifiedItem =
  | {kind: 'sms' | 'chat'; key: string; at: string; title: string; preview: string; paused: boolean; conv: Conversation}
  | {kind: 'email'; key: string; at: string; title: string; preview: string; draft: EmailDraft}
  | {kind: 'phone'; key: string; at: string; title: string; preview: string; call: PhoneCall; recording?: Recording}
  | {kind: MetaChannel; key: string; at: string; title: string; preview: string; meta: MetaConversation};

const AUTHOR_LABEL = {customer: 'Customer', ai: 'Concierge (AI)', owner: 'You'} as const;

/**
 * Unified omnichannel inbox: SMS, Website chat, Email drafts, Phone calls + voicemail playback,
 * and Meta messaging (Messenger, Instagram DMs, WhatsApp) in one list.
 */
export function Texts({token}: {token: string}) {
  const api = createApi(token);
  const [channel, setChannel] = useState<Channel>('all');
  const [phone, setPhone] = useState<Phone | null>(null);
  const [items, setItems] = useState<UnifiedItem[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('');
  const [thread, setThread] = useState<Thread | null>(null);
  const [metaThread, setMetaThread] = useState<MetaThread | null>(null);
  const [waTemplates, setWaTemplates] = useState<WaTemplate[]>([]);
  const [draft, setDraft] = useState('');
  const [audioUrl, setAudioUrl] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [role, setRole] = useState<string>('owner');
  const selectedRef = useRef('');
  selectedRef.current = selectedKey;

  useEffect(() => {
    api('/owner/me').then((me) => setRole((me as {role?: string}).role || 'owner')).catch(() => {});
  }, [token]);

  async function loadInbox() {
    try {
      const wantSms = channel === 'all' || channel === 'sms';
      const wantChat = channel === 'all' || channel === 'chat';
      const wantEmail = channel === 'all' || channel === 'email';
      const wantPhone = channel === 'all' || channel === 'phone';
      const wantMeta = channel === 'all' || channel === 'messenger' || channel === 'instagram' || channel === 'whatsapp';

      const [smsRes, chatRes, emailRes, callsRes, metaRes] = await Promise.all([
        wantSms ? api('/owner/sms/inbox').catch(() => ({conversations: []})) : Promise.resolve({conversations: []}),
        wantChat ? api('/owner/chat/inbox').catch(() => ({conversations: []})) : Promise.resolve({conversations: []}),
        wantEmail ? api('/owner/email-drafts').catch(() => ([])) : Promise.resolve([]),
        wantPhone ? api('/owner/phone-calls').catch(() => ([])) : Promise.resolve([]),
        wantMeta ? api('/owner/meta-messaging/conversations').catch(() => ({conversations: []})) : Promise.resolve({conversations: []}),
      ]);

      const smsData = smsRes as {phone?: Phone; conversations?: Conversation[]};
      if (wantSms && smsData.phone) setPhone(smsData.phone);
      const chatData = chatRes as {conversations?: Conversation[]};
      const drafts = Array.isArray(emailRes) ? (emailRes as EmailDraft[]) : ((emailRes as {drafts?: EmailDraft[]}).drafts || []);
      const calls = Array.isArray(callsRes) ? (callsRes as PhoneCall[]) : ((callsRes as {calls?: PhoneCall[]}).calls || []);
      const metaConvs = ((metaRes as {conversations?: MetaConversation[]}).conversations || []);

      const merged: UnifiedItem[] = [];
      for (const c of smsData.conversations || []) {
        merged.push({
          kind: 'sms', key: 'sms:' + c.id, at: c.last_at || '',
          title: c.name || c.phone || 'Unknown number',
          preview: `${AUTHOR_LABEL[c.last_author]}: ${c.last_text}`,
          paused: c.paused, conv: c,
        });
      }
      for (const c of chatData.conversations || []) {
        merged.push({
          kind: 'chat', key: 'chat:' + c.id, at: c.last_at || '',
          title: c.name || c.phone || 'Website visitor',
          preview: `${AUTHOR_LABEL[c.last_author]}: ${c.last_text}`,
          paused: c.paused, conv: c,
        });
      }
      for (const d of drafts) {
        merged.push({
          kind: 'email', key: 'email:' + d.id, at: d.created_at || '',
          title: d.sender || 'Email enquiry',
          preview: d.subject || d.inbound_body.slice(0, 80),
          draft: d,
        });
      }
      for (const call of calls) {
        const rec: Recording | undefined = call.session_id
          ? {session_id: call.session_id, conversation_id: '', mime_type: 'audio/ogg', created_at: call.started_at || ''}
          : undefined;
        merged.push({
          kind: 'phone', key: 'phone:' + call.call_sid, at: call.started_at || '',
          title: call.from_number || 'Phone caller',
          preview: call.summary || `${call.status}${call.duration_seconds ? ` (${call.duration_seconds}s)` : ''}`,
          call, recording: rec,
        });
      }
      for (const mc of metaConvs) {
        if (channel !== 'all' && channel !== mc.channel) continue;
        merged.push({
          kind: mc.channel,
          key: `meta:${mc.channel}:${mc.sender_id}`,
          at: mc.last_at || '',
          title: mc.sender_name || mc.sender_id,
          preview: `${mc.last_direction === 'out' ? 'You' : 'Customer'}: ${mc.last_text}`,
          meta: mc,
        });
      }
      merged.sort((a, b) => (b.at || '').localeCompare(a.at || ''));
      setItems(merged);
      if (!selectedRef.current && merged.length) setSelectedKey(merged[0].key);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load your inbox');
    }
  }

  const activeItem = items.find((i) => i.key === selectedKey) || null;
  const isMetaItem = (item: UnifiedItem | null): item is Extract<UnifiedItem, {kind: MetaChannel}> =>
    Boolean(item && (item.kind === 'whatsapp' || item.kind === 'messenger' || item.kind === 'instagram'));

  async function loadThread(item: UnifiedItem | null) {
    if (!item) {
      setThread(null);
      setMetaThread(null);
      return;
    }
    if (isMetaItem(item)) {
      setThread(null);
      try {
        const mt = await api(
          `/owner/meta-messaging/conversations/${item.meta.channel}/${encodeURIComponent(item.meta.sender_id)}`,
        ) as MetaThread;
        setMetaThread(mt);
        if (item.meta.channel === 'whatsapp' && !mt.window_open) {
          const tplRes = await api('/owner/meta-messaging/whatsapp/templates').catch(() => ({templates: []})) as {templates?: WaTemplate[]};
          setWaTemplates(tplRes.templates || []);
        } else {
          setWaTemplates([]);
        }
      } catch (e) {
        setStatus(e instanceof Error ? e.message : 'Could not load that conversation');
      }
      return;
    }
    setMetaThread(null);
    setWaTemplates([]);
    if (item.kind !== 'sms' && item.kind !== 'chat') {
      setThread(null);
      return;
    }
    try {
      setThread(await api(`/owner/${item.kind}/conversations/${item.conv.id}`) as Thread);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load that conversation');
    }
  }

  useEffect(() => {
    setAudioUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return ''; });
    if (activeItem && activeItem.kind === 'phone' && activeItem.recording) {
      const sid = activeItem.recording.session_id;
      fetch(`/owner/voice-recordings/${encodeURIComponent(sid)}`, {headers: {Authorization: 'Bearer ' + token}})
        .then((r) => r.ok ? r.blob() : null)
        .then((blob) => { if (blob) setAudioUrl(URL.createObjectURL(blob)); })
        .catch(() => {});
    }
  }, [selectedKey, token]);

  useEffect(() => {
    selectedRef.current = '';
    setSelectedKey(''); setThread(null); setItems([]); setStatus('');
    void loadInbox();
    const timer = window.setInterval(() => { void loadInbox(); }, 15000);
    return () => window.clearInterval(timer);
  }, [token, channel]);

  useEffect(() => { void loadThread(activeItem); }, [selectedKey]);

  async function setTakeover(paused: boolean) {
    if (!thread || !activeItem || (activeItem.kind !== 'sms' && activeItem.kind !== 'chat')) return;
    setBusy(true);
    try {
      await api(`/owner/${activeItem.kind}/conversations/${thread.id}/takeover`, 'POST', {paused});
      setStatus(paused ? 'You have taken over. Concierge will not reply to this person until you hand back.'
                       : 'Handed back. Concierge will answer this person again.');
      await Promise.all([loadThread(activeItem), loadInbox()]);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not change who is replying'); }
    finally { setBusy(false); }
  }

  async function send(value: string) {
    const text = value.trim();
    if (!thread || !text || !activeItem || (activeItem.kind !== 'sms' && activeItem.kind !== 'chat')) return;
    setBusy(true);
    try {
      const result = await api(`/owner/${activeItem.kind}/conversations/${thread.id}/reply`, 'POST',
        {text, request_id: crypto.randomUUID()}) as {status: string};
      setDraft('');
      setStatus(activeItem.kind === 'chat'
        ? 'Sent. The visitor sees it in their chat within a few seconds.'
        : result.status === 'queued'
        ? 'Sent to your phone to text out. It goes within a few seconds while the phone link is on.'
        : 'Sent.');
      await Promise.all([loadThread(activeItem), loadInbox()]);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send that reply'); }
    finally { setBusy(false); }
  }

  async function sendMetaReply(value: string, template?: WaTemplate) {
    if (!metaThread || !activeItem || !isMetaItem(activeItem)) return;
    const text = value.trim();
    if (!text && !template) return;
    setBusy(true);
    setStatus('');
    try {
      await api(
        `/owner/meta-messaging/conversations/${metaThread.channel}/${encodeURIComponent(metaThread.sender_id)}/reply`,
        'POST',
        template
          ? {template_name: template.name, template_language: template.language}
          : {text},
      );
      setDraft('');
      setStatus(template ? `Sent WhatsApp template "${template.name}".` : 'Reply sent.');
      await Promise.all([loadThread(activeItem), loadInbox()]);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not send Meta reply');
    } finally {
      setBusy(false);
    }
  }

  async function handleEmailAction(draftId: number, action: 'approve' | 'discard') {
    setBusy(true);
    try {
      await api(`/owner/email-drafts/${draftId}/${action}`, 'POST', {});
      setStatus(action === 'approve' ? 'Email approved and queued to send.' : 'Email draft discarded.');
      await loadInbox();
    } catch (e) {
      setStatus(e instanceof Error ? e.message : `Could not ${action} email draft`);
    } finally {
      setBusy(false);
    }
  }

  const offline = phone && phone.transport === 'device' && phone.paired && !phone.online;

  return (
    <VStack gap={4} style={{padding: 16}}>
      <HStack gap={2} role="group" aria-label="Inbox channel" style={{flexWrap: 'wrap'}}>
        <Button label="All" variant={channel === 'all' ? 'primary' : 'secondary'} onClick={() => setChannel('all')} />
        <Button label="Texts" variant={channel === 'sms' ? 'primary' : 'secondary'} onClick={() => setChannel('sms')} />
        <Button label="Website chat" variant={channel === 'chat' ? 'primary' : 'secondary'} onClick={() => setChannel('chat')} />
        <Button label="Email" variant={channel === 'email' ? 'primary' : 'secondary'} onClick={() => setChannel('email')} />
        <Button label="Phone & Voicemail" variant={channel === 'phone' ? 'primary' : 'secondary'} onClick={() => setChannel('phone')} />
        <Button label="Messenger" variant={channel === 'messenger' ? 'primary' : 'secondary'} onClick={() => setChannel('messenger')} />
        <Button label="Instagram" variant={channel === 'instagram' ? 'primary' : 'secondary'} onClick={() => setChannel('instagram')} />
        <Button label="WhatsApp" variant={channel === 'whatsapp' ? 'primary' : 'secondary'} onClick={() => setChannel('whatsapp')} />
      </HStack>
      {(channel === 'sms' || channel === 'all') && phone ? (
        <HStack gap={2} style={{alignItems: 'center', flexWrap: 'wrap'}}>
          <Badge label={phone.transport === 'device' ? (phone.paired ? (phone.online ? 'Phone link online' : 'Phone offline') : 'No phone paired')
                        : 'Texting: ' + phone.transport}
                 variant={offline || (phone.transport === 'device' && !phone.paired) ? 'error' : 'success'} />
          {phone.last_seen ? <Text>Last heard from <Timestamp value={phone.last_seen} /></Text> : null}
          {phone.receive_verified === false ? <Badge label="No text received yet" variant="warning" /> : null}
        </HStack>
      ) : null}
      {(channel === 'sms' || channel === 'all') && offline ? <StatusLine tone="warning" text="Your phone link is offline, so new texts are not reaching Concierge and replies wait. Open the Mac and check the Trendi Phone Connector is running." /> : null}
      <StatusLine text={status} />
      <div style={{display: 'flex', flexWrap: 'wrap', gap: 16, minHeight: 520, alignItems: 'flex-start'}}>
        <VStack gap={1} role="list" aria-label="Unified inbox conversations" style={{overflowY: 'auto', maxHeight: 640, flex: '0 1 320px', minWidth: 230}}>
          {items.length === 0 ? <Text>No conversations in this channel yet.</Text> : null}
          {items.map((item) => (
            <button key={item.key} type="button" role="listitem" className="c-nav-item" data-active={item.key === selectedKey}
                    aria-current={item.key === selectedKey ? 'true' : undefined} onClick={() => setSelectedKey(item.key)}
                    style={{textAlign: 'left', padding: 10, borderRadius: 8, display: 'block', width: '100%'}}>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center'}}>
                <strong>{item.title}</strong>
                <Badge label={item.kind.toUpperCase()} variant={item.kind === 'phone' ? 'warning' : item.kind === 'email' ? 'purple' : 'info'} />
              </HStack>
              <div style={{opacity: .75, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
                {item.preview}
              </div>
              {item.at ? <div style={{opacity: .6, fontSize: 12}}><Timestamp value={item.at} /></div> : null}
            </button>
          ))}
        </VStack>
        <div style={{display: 'flex', flexDirection: 'column', minHeight: 520, flex: '1 1 420px', minWidth: 0}}>
          {activeItem && (activeItem.kind === 'sms' || activeItem.kind === 'chat') && thread ? (
            <>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', paddingBottom: 8, flexWrap: 'wrap'}}>
                <Heading level={3}>{activeItem.title}</Heading>
                {role !== 'viewer' ? (thread.paused
                  ? <Button label="Hand back to Concierge" variant="secondary" isDisabled={busy} onClick={() => setTakeover(false)} />
                  : <Button label="Take over" variant="primary" isDisabled={busy} onClick={() => setTakeover(true)} />) : null}
              </HStack>
              <div style={{flex: 1, minHeight: 420}}>
                <ChatLayout
                  composer={role === 'viewer'
                    ? <ChatSystemMessage>View-only account: editors and owners can reply or take over.</ChatSystemMessage>
                    : thread.opted_out
                    ? <ChatSystemMessage>This person replied STOP, so they cannot be texted.</ChatSystemMessage>
                    : <ChatComposer value={draft} onChange={setDraft} onSubmit={send} isDisabled={busy}
                                    placeholder={thread.paused ? 'Reply to this customer yourself' : 'Type to reply yourself (this takes over from Concierge)'} />}>
                  <ChatMessageList emptyState={<Text>No messages yet.</Text>}>
                    {thread.paused ? <ChatSystemMessage variant="divider">You are replying. Concierge is paused for this person.</ChatSystemMessage> : null}
                    {thread.messages.map((m) => (
                      <ChatMessage key={m.id} sender={m.author === 'customer' ? 'assistant' : 'user'}
                                   name={AUTHOR_LABEL[m.author]}
                                   metadata={<ChatMessageMetadata timestamp={<Timestamp value={m.at} />} />}>
                        <ChatMessageBubble variant={m.author === 'customer' ? 'ghost' : 'filled'}>{m.text}</ChatMessageBubble>
                      </ChatMessage>
                    ))}
                  </ChatMessageList>
                </ChatLayout>
              </div>
            </>
          ) : activeItem && activeItem.kind === 'email' ? (
            <VStack gap={3} style={{padding: 16, border: '1px solid var(--color-border)', borderRadius: 12}}>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center'}}>
                <Heading level={3}>{activeItem.draft.subject || '(No subject)'}</Heading>
                <Badge label={activeItem.draft.status} variant="info" />
              </HStack>
              <Text><strong>From:</strong> {activeItem.draft.sender}</Text>
              <div style={{whiteSpace: 'pre-wrap', padding: 12, background: 'var(--color-surface-subtle, #f6f8fa)', borderRadius: 8}}>
                {activeItem.draft.inbound_body}
              </div>
              <Heading level={4}>AI Draft Reply</Heading>
              <div style={{whiteSpace: 'pre-wrap', padding: 12, border: '1px solid var(--color-border)', borderRadius: 8}}>
                {activeItem.draft.reply_body}
              </div>
              {role !== 'viewer' && activeItem.draft.status === 'draft' ? (
                <HStack gap={2}>
                  <Button label="Approve & send" variant="primary" isDisabled={busy} onClick={() => void handleEmailAction(activeItem.draft.id, 'approve')} />
                  <Button label="Discard" variant="secondary" isDisabled={busy} onClick={() => void handleEmailAction(activeItem.draft.id, 'discard')} />
                </HStack>
              ) : null}
            </VStack>
          ) : activeItem && activeItem.kind === 'phone' ? (
            <VStack gap={3} style={{padding: 16, border: '1px solid var(--color-border)', borderRadius: 12}}>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center'}}>
                <Heading level={3}>{activeItem.call.from_number || 'Phone call'}</Heading>
                <Badge label={activeItem.call.status || 'completed'} variant="warning" />
              </HStack>
              {activeItem.call.started_at ? <Text>Started <Timestamp value={activeItem.call.started_at} /></Text> : null}
              {activeItem.call.summary ? <Text>{activeItem.call.summary}</Text> : null}
              {audioUrl ? (
                <VStack gap={1}>
                  <Heading level={4}>Voicemail / Call Recording</Heading>
                  <audio controls src={audioUrl} style={{width: '100%'}} />
                </VStack>
              ) : (
                <Text>No audio recording stored for this call.</Text>
              )}
            </VStack>
          ) : isMetaItem(activeItem) && metaThread ? (
            <>
              <HStack gap={2} style={{justifyContent: 'space-between', alignItems: 'center', paddingBottom: 8, flexWrap: 'wrap'}}>
                <Heading level={3}>{activeItem.title}</Heading>
                <HStack gap={2} style={{alignItems: 'center'}}>
                  <Badge label={metaThread.channel.toUpperCase()} variant="info" />
                  <Badge
                    label={metaThread.window_open ? '24h reply window open' : '24h window closed'}
                    variant={metaThread.window_open ? 'success' : 'warning'}
                  />
                </HStack>
              </HStack>
              <div style={{flex: 1, minHeight: 420}}>
                <ChatLayout
                  composer={role === 'viewer'
                    ? <ChatSystemMessage>View-only account: editors and owners can reply.</ChatSystemMessage>
                    : metaThread.window_open
                    ? <ChatComposer value={draft} onChange={setDraft} onSubmit={(v) => void sendMetaReply(v)} isDisabled={busy}
                                    placeholder={`Reply on ${metaThread.channel}`} />
                    : metaThread.channel === 'whatsapp' && waTemplates.length > 0
                    ? <VStack gap={2} style={{padding: 8}}>
                        <Text>WhatsApp&apos;s 24-hour window has closed. Send an approved template:</Text>
                        <HStack gap={2} style={{flexWrap: 'wrap'}}>
                          {waTemplates.map((tpl) => (
                            <Button key={`${tpl.name}:${tpl.language}`} label={`${tpl.name} (${tpl.language})`}
                                    variant="secondary" isDisabled={busy} onClick={() => void sendMetaReply('', tpl)} />
                          ))}
                        </HStack>
                      </VStack>
                    : <ChatSystemMessage>
                        {metaThread.channel === 'whatsapp'
                          ? 'WhatsApp’s 24-hour customer service window has closed and no approved WhatsApp templates are configured yet. You can reply once the customer messages again.'
                          : 'Meta’s 24-hour customer messaging window has closed. You can reply once the customer messages you again.'}
                      </ChatSystemMessage>}>
                  <ChatMessageList emptyState={<Text>No messages yet.</Text>}>
                    {metaThread.messages.map((m) => (
                      <ChatMessage key={m.id} sender={m.direction === 'in' ? 'assistant' : 'user'}
                                   name={m.direction === 'in' ? (metaThread.sender_name || 'Customer') : 'You'}
                                   metadata={<ChatMessageMetadata timestamp={<Timestamp value={m.created_at} />} />}>
                        <ChatMessageBubble variant={m.direction === 'in' ? 'ghost' : 'filled'}>{m.text}</ChatMessageBubble>
                      </ChatMessage>
                    ))}
                  </ChatMessageList>
                </ChatLayout>
              </div>
            </>
          ) : (
            <Text>Select a conversation on the left to read it or reply.</Text>
          )}
        </div>
      </div>
    </VStack>
  );
}

export default Texts;
