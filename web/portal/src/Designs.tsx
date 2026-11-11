import {useEffect, useRef, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Badge} from '@astryxdesign/core/Badge';

type Design = {id: string; filename: string; size_bytes: number; status: string; summary?: Record<string, unknown> | null; created_at: string};

function money(cents: number, currency: string) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency: currency || 'USD'}).format((cents || 0) / 100);
}

export default function Designs({token}: {token: string}) {
  async function api(path: string, method = "GET", body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {Accept: "application/json", ...(body === undefined ? {} : {"Content-Type": "application/json"}), Authorization: "Bearer " + token},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  }
  const [designs, setDesigns] = useState<Design[]>([]);
  const [status, setStatus] = useState('');
  const [viewUrl, setViewUrl] = useState('');
  const [viewName, setViewName] = useState('');
  const [busy, setBusy] = useState(false);
  const viewerRef = useRef<HTMLDivElement>(null);
  const [link, setLink] = useState('');
  const [draft, setDraft] = useState<{title: string; currency: string; source: string; warnings?: string[]; lines: Array<{description: string; quantity: string; unit_price_cents: number; amount_cents: number}>; subtotal_cents: number; total_cents: number} | null>(null);

  async function load() {
    try { setDesigns(await api('/owner/designs') as Design[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load designs'); }
  }
  useEffect(() => { load(); }, [token]);

  useEffect(() => {
    let disposed = false;
    if (!viewUrl || !viewerRef.current) return;
    import('online-3d-viewer').then((mod) => {
      if (disposed || !viewerRef.current) return;
      const Viewer = (mod as unknown as {EmbeddedViewer: new (el: HTMLElement, params: object) => {LoadModelFromUrlList: (urls: string[]) => void}}).EmbeddedViewer;
      const viewer = new Viewer(viewerRef.current, {});
      viewer.LoadModelFromUrlList([viewUrl]);
    }).catch(() => setStatus('The 3D viewer could not load; download the file instead.'));
    return () => { disposed = true; if (viewerRef.current) viewerRef.current.innerHTML = ''; };
  }, [viewUrl]);

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
        if (viewUrl) URL.revokeObjectURL(viewUrl);
        setViewUrl(url); setViewName(design.filename);
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
    <div style={{maxWidth: 1040, margin: '0 auto', padding: '0 24px 48px'}}>
      <Heading level={1}>Designs and CAD</Heading>
      <p>Upload plans or 3D models, view them, and read wall areas from IFC models for cladding quotes.</p>
      <Card>
        <Heading level={2}>Customer upload link</Heading>
        <p>Send this to a customer so they can upload their own plans. It expires in 7 days.</p>
        <Button label="Create upload link" variant="secondary" onClick={async () => {
          try {
            const result = await api('/owner/designs/link', 'POST') as {url: string};
            const url = location.origin + result.url;
            setLink(url);
            navigator.clipboard?.writeText(url);
            setStatus('Upload link created and copied.');
          } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not create the link'); }
        }} />
        {link ? <p><a href={link} target="_blank" rel="noopener noreferrer">{link}</a></p> : null}
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
            {design.filename.toLowerCase().endsWith('.ifc') ? <Button label="IFC takeoff" variant="primary" onClick={() => takeoff(design)} /> : null}
            {design.summary ? <Button label="Draft quote" variant="secondary" onClick={() => quoteFromTakeoff(design)} /> : null}
            {design.summary ? <p>{String((design.summary as Record<string, unknown>).gross_wall_area_m2 ?? '')} m² gross · {String((design.summary as Record<string, unknown>).net_cladding_area_m2 ?? '')} m² cladding</p> : null}
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
      {viewUrl ? <Card><Heading level={2}>{viewName}</Heading><div ref={viewerRef} style={{height: 520, width: '100%'}} /><Button label="Close viewer" variant="ghost" onClick={() => { setViewUrl(''); setViewName(''); }} /></Card> : null}
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}


