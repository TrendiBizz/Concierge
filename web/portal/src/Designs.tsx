import {useEffect, useRef, useState} from 'react';
import {describeFailure} from './api';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Badge} from '@astryxdesign/core/Badge';
import {TextInput} from '@astryxdesign/core/TextInput';
import {StatusLine} from './StatusLine';
import {copyText} from './clipboard';

type Profile = {id: string; name: string; unit: string; rate_cents: number; waste_percent: string; minimum_cents: number; measurement: string; currency: string; is_default: boolean};
type Customer = {id: string; name?: string; email?: string; phone?: string; channel: string};
type Design = {id: string; filename: string; size_bytes: number; status: string; summary?: Record<string, unknown> | null; created_at: string};

function money(cents: number, currency: string) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency: currency || 'USD'}).format((cents || 0) / 100);
}

export default function Designs({token, onOpenQuotes}: {token: string; onOpenQuotes?: () => void}) {
  async function api(path: string, method = "GET", body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {Accept: "application/json", ...(body === undefined ? {} : {"Content-Type": "application/json"}), Authorization: "Bearer " + token},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
    return data;
  }
  const [designs, setDesigns] = useState<Design[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState('');
  const [rateDollars, setRateDollars] = useState('');
  const [waste, setWaste] = useState('');
  const [minimum, setMinimum] = useState('');
  const [status, setStatus] = useState('');
  const [viewFile, setViewFile] = useState<File | null>(null);
  const [viewName, setViewName] = useState('');
  const [busy, setBusy] = useState(false);
  const [quotedOnce, setQuotedOnce] = useState(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const [link, setLink] = useState('');
  const [draft, setDraft] = useState<{title: string; currency: string; source: string; warnings?: string[]; lines: Array<{description: string; quantity: string; unit_price_cents: number; amount_cents: number}>; subtotal_cents: number; total_cents: number} | null>(null);

  async function load() {
    try { setDesigns(await api('/owner/designs') as Design[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load designs'); }
  }

  const defaultProfile = profiles.find((p) => p.is_default) || profiles[0];

  async function loadPricing() {
    try {
      const rows = await api('/owner/quote-profiles') as Profile[];
      setProfiles(rows);
      const chosen = rows.find((p) => p.is_default) || rows[0];
      if (chosen) {
        setRateDollars((chosen.rate_cents / 100).toFixed(2));
        setWaste(String(Number(chosen.waste_percent)));
        setMinimum((chosen.minimum_cents / 100).toFixed(2));
      }
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load your rates'); }
  }

  async function loadCustomers() {
    // The CRM list endpoint is /owner/crm; it returns leads alongside appointments and tasks.
    try {
      const data = await api('/owner/crm') as {leads?: Customer[]};
      setCustomers(data.leads || []);
    } catch { setCustomers([]); }
  }

  async function saveRate() {
    const body = {
      name: defaultProfile?.name || 'Measured work',
      unit: 'm²',
      rate_cents: Math.round(Number(rateDollars || '0') * 100),
      waste_percent: Number(waste || '0'),
      minimum_cents: Math.round(Number(minimum || '0') * 100),
      measurement: defaultProfile?.measurement || 'net_cladding',
      currency: defaultProfile?.currency || 'NZD',
      tax_basis_points: 1500,
      is_default: true,
      active: true,
    };
    try {
      if (defaultProfile) await api('/owner/quote-profiles/' + defaultProfile.id, 'PATCH', body);
      else await api('/owner/quote-profiles', 'POST', body);
      await loadPricing();
      setStatus('Saved. Quotations from a measured model use these rates.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save your rates'); }
  }

  async function quoteModel(design: Design) {
    if (!customerId) { setStatus('Choose which customer this quote is for.'); return; }
    setBusy(true); setStatus('Pricing the measured area…');
    try {
      const result = await api('/owner/designs/' + design.id + '/quote', 'POST', {lead_id: customerId}) as {quotation: {id: string; title: string; total_cents: number; currency: string}; billed_area: string; notes: string[]};
      setQuotedOnce(true);
      setStatus('Quotation drafted: ' + result.quotation.title + ' — ' + money(result.quotation.total_cents, result.quotation.currency) + ' for ' + result.billed_area + ' m². ' + (result.notes.join(' ') || '') + ' Review it in Quotes.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not price this model'); }
    setBusy(false);
  }
  useEffect(() => { load(); void loadPricing(); void loadCustomers(); }, [token]);

  useEffect(() => {
    let disposed = false;
    if (!viewFile || !viewerRef.current) return;
    import('online-3d-viewer').then((mod) => {
      if (disposed || !viewerRef.current) return;
      const Viewer = (mod as unknown as {EmbeddedViewer: new (el: HTMLElement, params: object) => {LoadModelFromFileList: (files: File[]) => void}}).EmbeddedViewer;
      const viewer = new Viewer(viewerRef.current, {});
      // A blob: URL carries no filename, so the viewer could not tell an STL from a PDF and said
      // "No importable file found." for every model. A File keeps its real name and extension.
      viewer.LoadModelFromFileList([viewFile]);
    }).catch(() => setStatus('The 3D viewer could not load; download the file instead.'));
    return () => { disposed = true; if (viewerRef.current) viewerRef.current.innerHTML = ''; };
  }, [viewFile]);

  async function upload(file: File) {
    setBusy(true); setStatus('');
    try {
      const response = await fetch('/owner/designs?filename=' + encodeURIComponent(file.name), {
        method: 'POST', headers: {Authorization: 'Bearer ' + token, 'Content-Type': file.type || 'application/octet-stream'}, body: file});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Upload failed');
      setStatus(file.name + ' uploaded.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Upload failed'); }
    setBusy(false);
  }

  async function open(design: Design, download = false) {
    setStatus('');
    try {
      const response = await fetch('/owner/designs/' + design.id + '/file', {headers: {Authorization: 'Bearer ' + token}});
      if (!response.ok) throw new Error('File unavailable');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      if (download) { const link = document.createElement('a'); link.href = url; link.download = design.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 30000); return; }
      const ext = design.filename.split('.').pop()?.toLowerCase() || '';
      if (['ifc', 'glb', 'gltf', 'obj', 'stl', '3dm', 'step', 'stp', 'dae', 'fbx'].includes(ext)) {
        URL.revokeObjectURL(url);
        setViewFile(new File([blob], design.filename, {type: blob.type}));
        setViewName(design.filename);
      } else {
        window.open(url, '_blank', 'noopener');
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      }
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not open the design'); }
  }

  async function takeoff(design: Design) {
    setBusy(true); setStatus('Reading the IFC…');
    try {
      const summary = await api('/owner/designs/' + design.id + '/takeoff', 'POST') as Record<string, unknown>;
      setStatus('Wall area: ' + String(summary.gross_wall_area_m2 ?? '—') + ' m² gross · ' + String(summary.net_wall_area_m2 ?? '—') + ' m² net · ' + String(summary.opening_area_m2 ?? '—') + ' m² openings.' + (summary.note ? ' ' + String(summary.note) : ''));
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Takeoff failed'); }
    setBusy(false);
  }

  async function quoteFromTakeoff(design: Design) {
    setBusy(true); setStatus('Drafting a quotation from the measured areas…'); setDraft(null);
    try {
      const result = await api('/owner/crm/quotations/draft', 'POST', {design_id: design.id, currency: 'NZD'}) as NonNullable<typeof draft>;
      setDraft(result);
      setStatus((result.warnings || []).join(' ') || 'Draft ready. Open Quotes to edit and save it.');
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not draft a quotation'); }
    setBusy(false);
  }

  return (
    <div>
      <p>Upload plans or 3D models, view them, and read measured wall areas from an IFC model.</p>
      <Card>
        <Heading level={2}>Who is this for?</Heading>
        <p>A quotation has to belong to a customer. Pick one here, and "Price this model" below will draft the quote against them.</p>
        <select value={customerId} onChange={(e) => setCustomerId(e.target.value)} style={{padding: '8px 10px', minWidth: 280}}>
          <option value="">Choose a customer or enquiry…</option>
          {customers.map((c) => (
            <option key={c.id} value={c.id}>{[c.name || '(no name)', c.phone || c.email || ('via ' + c.channel)].filter(Boolean).join(' · ')}</option>
          ))}
        </select>
        {!customers.length ? <div className="c-empty"><strong>No enquiries yet</strong><p>As soon as a customer messages you, they appear here so you can pick the job and measure it.</p></div> : null}
      </Card>
      <Card>
        <Heading level={2}>Customer upload link</Heading>
        <p>Send this to a customer so they can upload their own plans. It expires in 7 days.</p>
        <Button label="Create upload link" variant="secondary" onClick={async () => {
          try {
            const result = await api('/owner/designs/link', 'POST') as {url: string};
            const url = location.origin + result.url;
            setLink(url);
            const copied = await copyText(url);
            setStatus(copied ? 'Upload link created and copied.' : 'Upload link created — copy it below.');
          } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not create the link'); }
        }} />
        {link ? <p><a href={link} target="_blank" rel="noopener noreferrer">{link}</a></p> : null}
      </Card>
      <Card>
        <Heading level={2}>New to this? Start here</Heading>
        <p>If your drawings come from a 3D model, Concierge can measure the wall area for you and price it at your rate. Four steps:</p>
        <ol>
          <li><strong>Install</strong> <a href="https://www.blender.org/download/" target="_blank" rel="noreferrer">Blender</a> (free) and the <a href="https://bonsaibim.org/" target="_blank" rel="noreferrer">Bonsai</a> add-on (free). Bonsai is what writes the wall areas we measure.</li>
          <li><strong>Draw</strong> the outside walls, cast them as walls, and cut doors and windows as openings.</li>
          <li><strong>Export</strong> as IFC4 with quantities switched on, then upload it below and press <em>Measure areas</em>.</li>
          <li><strong>Price</strong> it: set your rate in the card below, pick the customer, press <em>Price this model</em>.</li>
        </ol>
        <p><a href="/guide/bonsai-cladding" target="_blank" rel="noreferrer"><strong>Open the 3D model walkthrough (printable)</strong></a> — the same steps in detail, with what to check before you trust a number.</p>
      </Card>
      <Card>
        <Heading level={2}>How your quotes are worked out</Heading>
        <p>Measured models are priced by the square metre. Set your rate once; every quote from a model uses it.</p>
        <div style={{display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end'}}>
          <TextInput label="Rate per m² ($)" value={rateDollars} onChange={(value: string) => setRateDollars(value)} placeholder="45.00" />
          <TextInput label="Waste (%)" value={waste} onChange={(value: string) => setWaste(value)} placeholder="10" />
          <TextInput label="Minimum charge ($)" value={minimum} onChange={(value: string) => setMinimum(value)} placeholder="500.00" />
          <Button label="Save rates" variant="secondary" onClick={() => void saveRate()} />
        </div>
        <p style={{color: '#555'}}>{defaultProfile ? 'Currently: ' + defaultProfile.name + ' at ' + money(defaultProfile.rate_cents, defaultProfile.currency) + '/' + defaultProfile.unit + (Number(defaultProfile.waste_percent) ? ' with ' + Number(defaultProfile.waste_percent) + '% waste' : '') + (defaultProfile.minimum_cents ? ', minimum ' + money(defaultProfile.minimum_cents, defaultProfile.currency) : '') + '. Measured on the ' + defaultProfile.measurement.replace('_', ' ') + ' area.' : 'No rate yet — set one above and a measured model becomes a priced quotation.'}</p>
      </Card>
      <Card>
        <Heading level={2}>Upload a design</Heading>
        <input type="file" accept=".pdf,.dwg,.dxf,.ifc,.glb,.gltf,.obj,.stl,.3dm,.step,.stp" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
        <p>PDF, DWG, IFC, GLB/GLTF, OBJ, STL, 3DM, STEP up to 50 MB. IFC gives automatic wall-area takeoff.</p>
      </Card>
      <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))'}}>
        {designs.map((design) => (
          <Card key={design.id}>
            <strong>{design.filename}</strong>
            <p>{Math.round(design.size_bytes / 1024)} KB · <Badge label={design.status} variant={design.status === 'parsed' ? 'success' : design.status === 'failed' ? 'error' : 'neutral'} /> · {new Date(design.created_at).toLocaleDateString()}</p>
            <Button label="View" variant="secondary" onClick={() => open(design)} />
            <Button label="Download" variant="ghost" onClick={() => open(design, true)} />
            {design.filename.toLowerCase().endsWith('.ifc') ? <Button label="Measure areas" variant="primary" onClick={() => takeoff(design)} /> : null}
            {design.summary ? <Button label="Draft quote" variant="secondary" onClick={() => quoteFromTakeoff(design)} /> : null}
            {design.summary ? <Button label="Price this model" variant="primary" onClick={() => void quoteModel(design)} /> : null}
            {design.summary ? <p>{String((design.summary as Record<string, unknown>).gross_wall_area_m2 ?? '')} m² gross · {String((design.summary as Record<string, unknown>).net_cladding_area_m2 ?? '')} m² net</p> : null}
          </Card>
        ))}
        {!designs.length ? <p>No designs uploaded yet.</p> : null}
      </div>
      {draft ? (
        <Card>
          <Heading level={2}>{draft.title}</Heading>
          <p>Drafted from the IFC takeoff ({draft.source === 'model' ? 'AI, catalogue prices' : 'measured areas'}). Nothing is saved yet — open Quotes to edit and save it.</p>
          <ul>
            {draft.lines.map((line, index) => (
              <li key={index}>{line.description} · {line.quantity} × {money(line.unit_price_cents, draft.currency)} = {money(line.amount_cents, draft.currency)}</li>
            ))}
          </ul>
          <p><strong>Subtotal {money(draft.subtotal_cents, draft.currency)} · Total {money(draft.total_cents, draft.currency)}</strong></p>
        </Card>
      ) : null}
      {viewFile ? <Card><Heading level={2}>{viewName}</Heading><div ref={viewerRef} style={{height: 520, width: '100%'}} /><Button label="Close viewer" variant="ghost" onClick={() => { setViewFile(null); setViewName(''); }} /></Card> : null}
      {<StatusLine text={status} />}
      {quotedOnce && onOpenQuotes ? <p><Button label="Open Quotes to review or send it" variant="primary" onClick={onOpenQuotes} /></p> : null}
    </div>
  );
}


