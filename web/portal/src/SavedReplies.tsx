import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';
import {HStack} from '@astryxdesign/core/HStack';
import {createApi as useApi} from './api';
import {StatusLine} from './StatusLine';

type Template = {id: string; name: string; subject: string; body: string};

/**
 * Saved replies, so the same follow-up is not retyped every time.
 *
 * Templates existed only as a single column per tenant (one SMS template, one missed-call
 * template); there was no library and no way to reuse a quote follow-up.
 */
export function SavedReplies({token}: {token: string}) {
  const api = useApi(token);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [name, setName] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [status, setStatus] = useState('');

  async function load() {
    try { setTemplates(await api('/owner/email-templates') as Template[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load your saved replies'); }
  }
  useEffect(() => { load(); }, [token]);

  async function add() {
    if (!name.trim() || !body.trim()) { setStatus('A saved reply needs a name and a body.'); return; }
    try {
      await api('/owner/email-templates', 'POST', {name: name.trim(), subject: subject.trim(), body});
      setName(''); setSubject(''); setBody('');
      setStatus('Saved. You can now use it on any reply.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save that reply'); }
  }

  async function remove(template: Template) {
    try {
      await api('/owner/email-templates/' + template.id, 'DELETE');
      setStatus('Deleted.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not delete that reply'); }
  }

  return (
    <Card>
      <Heading level={2}>Saved replies</Heading>
      <Text size="sm" color="secondary">
        The messages you send over and over — a quote follow-up, a reminder, a thanks. Write once,
        reuse it with the customer's name filled in.
      </Text>
      <VStack gap={2}>
        <TextInput label="What do you call it?" value={name} onChange={setName}
                   placeholder="Quote follow-up" />
        <TextInput label="Subject (optional)" value={subject} onChange={setSubject} />
        <TextArea label="The message" value={body} onChange={setBody}
                  placeholder="Hi, just checking you saw the quote I sent through. Happy to answer anything." />
        <Button label="Save this reply" variant="primary" onClick={() => void add()} />
      </VStack>
      {templates.length ? (
        <VStack gap={2}>
          {templates.map((template) => (
            <HStack key={template.id} gap={3} vAlign="center" style={{flexWrap: 'wrap'}}>
              <strong>{template.name}</strong>
              <Text size="sm" color="secondary">{template.body.slice(0, 80)}</Text>
              <Button label="Delete" variant="ghost" onClick={() => void remove(template)} />
            </HStack>
          ))}
        </VStack>
      ) : <Text size="sm" color="secondary">No saved replies yet.</Text>}
      <StatusLine text={status} />
    </Card>
  );
}
