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

type Doc = {document_id: string; title: string; chunks: number};

/**
 * What Concierge knows about the business.
 *
 * A new business started with an assistant that knew nothing: the website import and the document
 * endpoints existed, but Studio had no screen for them, so the only way to teach it was the legacy
 * owner page. This is that screen: read your own website, add a note, remove what is wrong.
 */
export function Knowledge({token}: {token: string}) {
  const api = useApi(token);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setDocs(await api('/owner/knowledge') as Doc[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load what Concierge knows'); }
  }
  useEffect(() => { void load(); }, [token]);

  async function importSite() {
    setBusy(true); setStatus('Reading your website. This can take up to a minute…');
    try {
      const result = await api('/owner/knowledge/import-website', 'POST') as {pages?: number; chunks?: number};
      setStatus('Done. Concierge read ' + (result.pages ?? 'your') + ' pages (' + (result.chunks ?? 0) + ' pieces of knowledge).');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not read your website'); }
    setBusy(false);
  }

  async function add() {
    if (!title.trim() || !text.trim()) { setStatus('Give the note a title and some text.'); return; }
    setBusy(true);
    try {
      await api('/owner/knowledge', 'POST', {title: title.trim(), text});
      setTitle(''); setText('');
      setStatus('Saved. Concierge will use this when it answers.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save that note'); }
    setBusy(false);
  }

  async function remove(doc: Doc) {
    try {
      await api('/owner/knowledge/' + doc.document_id, 'DELETE');
      setStatus('Removed.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not remove that note'); }
  }

  return (
    <VStack gap={3}>
      <Card>
        <Heading level={2}>Read my website</Heading>
        <Text size="sm" color="secondary">
          Concierge reads the public pages of your own website and learns your services, areas and
          prices from them. Run it again whenever your site changes.
        </Text>
        <Button label={busy ? 'Working…' : 'Read my website now'} variant="primary"
                onClick={() => void importSite()} />
      </Card>
      <Card>
        <Heading level={2}>Add your own note</Heading>
        <Text size="sm" color="secondary">
          Opening hours, what you do not do, how you handle call-outs — anything a customer asks.
        </Text>
        <VStack gap={2}>
          <TextInput label="Title" value={title} onChange={setTitle} placeholder="Call-out fees" />
          <TextArea label="What should Concierge know?" value={text} onChange={setText} />
          <Button label="Save this note" variant="primary" onClick={() => void add()} />
        </VStack>
      </Card>
      <Card>
        <Heading level={2}>Your notes</Heading>
        {docs.length ? (
          <VStack gap={2}>
            {docs.map((doc) => (
              <HStack key={doc.document_id} gap={3} vAlign="center" style={{flexWrap: 'wrap'}}>
                <strong>{doc.title}</strong>
                <Text size="sm" color="secondary">{doc.chunks} pieces</Text>
                <Button label="Remove" variant="ghost" onClick={() => void remove(doc)} />
              </HStack>
            ))}
          </VStack>
        ) : <Text size="sm" color="secondary">No notes yet. Pages read from your website are not listed here.</Text>}
        <StatusLine text={status} />
      </Card>
    </VStack>
  );
}
