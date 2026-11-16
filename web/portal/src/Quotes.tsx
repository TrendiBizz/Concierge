import {useEffect, useMemo, useState} from 'react';
import {describeFailure} from './api';
import {Badge} from '@astryxdesign/core/Badge';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {CheckboxInput} from '@astryxdesign/core/CheckboxInput';
import {DateInput} from '@astryxdesign/core/DateInput';
import {Dialog} from '@astryxdesign/core/Dialog';
import {Divider} from '@astryxdesign/core/Divider';
import {EmptyState} from '@astryxdesign/core/EmptyState';
import {Grid} from '@astryxdesign/core/Grid';
import {Heading} from '@astryxdesign/core/Heading';
import {HStack} from '@astryxdesign/core/HStack';
import {IconButton} from '@astryxdesign/core/IconButton';
import {MoreMenu} from '@astryxdesign/core/MoreMenu';
import {NumberInput} from '@astryxdesign/core/NumberInput';
import {Selector} from '@astryxdesign/core/Selector';
import {Text} from '@astryxdesign/core/Text';
import {TextArea} from '@astryxdesign/core/TextArea';
import {TextInput} from '@astryxdesign/core/TextInput';
import {VStack} from '@astryxdesign/core/VStack';
import {StatusLine} from './StatusLine';
import {Table, proportional} from '@astryxdesign/core/Table';
import type {TableColumn} from '@astryxdesign/core/Table';

type Brand = {name: string; accent: string; contact: string};
type Lead = {id: string; name?: string; email?: string; phone?: string; channel: string; status: string; created_at: string};
type Product = {id: string; name: string; sku?: string; unit?: string; sale_price_cents: number};
type Contact = {name?: string; company?: string; email?: string; phone?: string; address?: string};
type StoredLine = {description: string; quantity: string | number; unit?: string;
  unit_price_cents: number; discount_basis_points?: number; amount_cents?: number};
type Quote = {id: string; title: string; lead_id?: string | null; reference?: string; currency: string; status: string;
  payment_status?: string; lines: StoredLine[]; contact?: Contact; subtotal_cents: number;
  discount_cents?: number; discount_basis_points?: number; tax_cents: number; total_cents: number;
  tax_basis_points?: number; notes?: string; terms?: string; quote_date?: string;
  valid_until?: string; version: number; public_token?: string; sent_at?: string;
  viewed_at?: string | null; accepted_by_name?: string; accepted_at?: string; created_at: string};
type Business = {name?: string; gst_number?: string; nzbn?: string; business_address?: string;
  business_phone?: string; quote_terms?: string; quote_valid_days?: number;
  allow_deposit?: boolean; deposit_percent?: number; invoice_payment_terms_days?: number};
type Payment = {instructions?: string; url?: string; summary?: Record<string, number>};

type Line = {key: string; description: string; quantity: string; unit: string;
  price: string; discount: string};

const TAX_DEFAULT = 15;

function money(cents: number, currency: string) {
  const symbol = ({NZD: '$', USD: 'US$', AUD: 'A$', GBP: '£', EUR: '€', CAD: 'C$'} as Record<string, string>)[currency];
  const amount = new Intl.NumberFormat('en-NZ', {minimumFractionDigits: 2, maximumFractionDigits: 2}).format((cents || 0) / 100);
  return symbol ? symbol + amount : amount + ' ' + (currency || '');
}

/** Whole cents, half-up — the same rounding the API uses, so the screen never disagrees with the PDF. */
function cents(value: string | number) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number * 100) : 0;
}

function lineTotals(line: Line) {
  const gross = Math.round((Number(line.quantity) || 0) * cents(line.price));
  const discount = Math.round(gross * (Number(line.discount) || 0) / 100);
  return {gross, discount, amount: gross - discount};
}

function totalsFor(lines: Line[], discountPct: number, taxPct: number) {
  const subtotal = lines.reduce((sum, line) => sum + lineTotals(line).amount, 0);
  const discount = Math.round(subtotal * (Number(discountPct) || 0) / 100);
  const taxable = subtotal - discount;
  const tax = Math.round(taxable * (Number(taxPct) || 0) / 100);
  return {subtotal, discount, tax, total: taxable + tax};
}

function blankLine(): Line {
  return {key: Math.random().toString(36).slice(2), description: '', quantity: '1', unit: 'each', price: '', discount: '0'};
}

function lineFromStored(line: StoredLine): Line {
  return {
    key: Math.random().toString(36).slice(2),
    description: line.description,
    quantity: String(line.quantity ?? '1'),
    unit: line.unit || 'each',
    price: (Number(line.unit_price_cents || 0) / 100).toFixed(2),
    discount: String((Number(line.discount_basis_points || 0) / 100).toFixed(2)).replace(/\.00$/, ''),
  };
}

function iso(value?: string | null) {
  return value ? String(value).slice(0, 10) : undefined;
}

function today() {
  return new Date().toISOString().slice(0, 10);
}

function inDays(days: number) {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function statusVariant(status: string): 'success' | 'error' | 'info' | 'warning' | 'neutral' {
  return status === 'accepted' ? 'success' : status === 'declined' ? 'error'
    : status === 'reviewed' ? 'info' : status === 'sent' ? 'warning' : 'neutral';
}

const STATUS_LABEL: Record<string, string> = {
  draft: 'draft', reviewed: 'approved', sent: 'sent', accepted: 'accepted',
  declined: 'declined', void: 'void',
};

export function Quotes({token, onOpenDesigns}: {token: string; brand: Brand; onOpenDesigns?: () => void}) {
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [biz, setBiz] = useState<Business>({});
  const [pay, setPay] = useState<Payment>({});
  const [showSettings, setShowSettings] = useState(false);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Quote | null>(null);
  const [leadId, setLeadId] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Contact>({});
  const [title, setTitle] = useState('');
  const [currency, setCurrency] = useState('NZD');
  const [quoteDate, setQuoteDate] = useState<string>(today());
  const [validUntil, setValidUntil] = useState<string>(inDays(30));
  const [lines, setLines] = useState<Line[]>([blankLine()]);
  const [discountPct, setDiscountPct] = useState('0');
  const [taxPct, setTaxPct] = useState(String(TAX_DEFAULT));
  const [notes, setNotes] = useState('');
  const [terms, setTerms] = useState('');
  const [brief, setBrief] = useState('');
  const [draftNote, setDraftNote] = useState('');

  const [pendingSignoff, setPendingSignoff] = useState<Quote | null>(null);
  const [sendFor, setSendFor] = useState<Quote | null>(null);
  const [sendSubject, setSendSubject] = useState('');
  const [sendMessage, setSendMessage] = useState('');

  async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {'Accept': 'application/json', ...(body !== undefined ? {'Content-Type': 'application/json'} : {}),
        Authorization: 'Bearer ' + token},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
    return data;
  }

  async function load() {
    try {
      const [q, c, p, me, payment, business] = await Promise.all([
        api('/owner/crm/quotations'), api('/owner/crm'), api('/owner/products'),
        api('/owner/me'), api('/owner/payment-settings'), api('/owner/business')]);
      setQuotes(q as Quote[]);
      setLeads(((c as {leads?: Lead[]}).leads || []) as Lead[]);
      setProducts(p as Product[]);
      setRole((me as {role: string}).role);
      setPay(payment as Payment);
      setBiz(business as Business);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load quotations'); }
  }
  useEffect(() => { void load(); }, [token]);

  const live = useMemo(() => totalsFor(lines, Number(discountPct) || 0, Number(taxPct) || 0), [lines, discountPct, taxPct]);
  const openValue = quotes.filter((q) => ['reviewed', 'sent'].includes(q.status)).reduce((sum, q) => sum + q.total_cents, 0);
  const wonValue = quotes.filter((q) => q.status === 'accepted').reduce((sum, q) => sum + q.total_cents, 0);

  function resetEditor() {
    setEditing(null);
    setLeadId(null);
    setCustomer({});
    setTitle('');
    setQuoteDate(today());
    setValidUntil(inDays(Number(biz.quote_valid_days) || 30));
    setLines([blankLine()]);
    setDiscountPct('0');
    setTaxPct(String(TAX_DEFAULT));
    setNotes('');
    setTerms('');
    setBrief('');
    setDraftNote('');
  }

  function openNew() {
    resetEditor();
    setEditorOpen(true);
    setStatus('');
  }

  function openEdit(quote: Quote) {
    setEditing(quote);
    setLeadId(quote.lead_id || null);
    setCustomer({
      name: quote.contact?.name || '', company: quote.contact?.company || '',
      email: quote.contact?.email || '', phone: quote.contact?.phone || '',
      address: quote.contact?.address || ''});
    setTitle(quote.title || '');
    setCurrency(quote.currency || 'NZD');
    setQuoteDate(iso(quote.quote_date) || iso(quote.created_at) || today());
    setValidUntil(iso(quote.valid_until) || inDays(30));
    setLines((quote.lines || []).map(lineFromStored));
    setDiscountPct(String((Number(quote.discount_basis_points || 0) / 100).toFixed(2)).replace(/\.00$/, ''));
    setTaxPct(String((Number(quote.tax_basis_points ?? TAX_DEFAULT * 100) / 100).toFixed(2)).replace(/\.00$/, ''));
    setNotes(quote.notes || '');
    setTerms(quote.terms || '');
    setBrief('');
    setDraftNote('');
    setEditorOpen(true);
    setStatus('');
  }

  function pickLead(id: string | null) {
    setLeadId(id);
    const lead = leads.find((row) => row.id === id);
    if (lead) {
      setCustomer({...customer, name: lead.name || customer.name || '',
        email: lead.email || customer.email || '', phone: lead.phone || customer.phone || ''});
      if (!title && lead.name) setTitle(lead.name);
    }
  }

  function addProduct(id: string | null) {
    const product = products.find((item) => item.id === id);
    if (!product) return;
    setLines((current) => [...current.filter((line) => line.description.trim() || line.price), {
      key: Math.random().toString(36).slice(2),
      description: product.name,
      quantity: '1',
      unit: product.unit || 'each',
      price: (product.sale_price_cents / 100).toFixed(2),
      discount: '0',
    }]);
  }

  function updateLine(index: number, patch: Partial<Line>) {
    setLines((current) => current.map((line, i) => i === index ? {...line, ...patch} : line));
  }

  async function draftWithAi() {
    if (!leadId && !brief.trim()) { setDraftNote('Choose an enquiry or describe the job first.'); return; }
    setBusy(true); setDraftNote('');
    try {
      const result = await api('/owner/crm/quotations/draft', 'POST', {
        lead_id: leadId, brief, currency, tax_basis_points: Math.round((Number(taxPct) || 0) * 100),
      }) as {title: string; notes: string; lines: StoredLine[]; warnings?: string[]; source: string};
      setTitle(result.title);
      setNotes(result.notes || '');
      setLines(result.lines.map(lineFromStored));
      setDraftNote((result.warnings || []).join(' ') || (result.source === 'model'
        ? 'Drafted from your catalogue and this enquiry. Check every line, unit price and quantity — you are signing it off, not the AI.'
        : 'Drafted from the measured takeoff. Check every line before you approve it.'));
    } catch (e) { setDraftNote(e instanceof Error ? e.message : 'Could not draft the quotation'); }
    setBusy(false);
  }

  async function save(thenReview = false) {
    const usable = lines.filter((line) => line.description.trim());
    if (!usable.length) { setStatus('Add at least one line before saving the quotation.'); return; }
    if (!leadId && !customer.name && !customer.email) {
      setStatus('Choose an enquiry or enter the customer this quote is for.'); return;
    }
    setBusy(true); setStatus('');
    const body = {
      lead_id: leadId || null,
      customer,
      title: title.trim() || 'Quotation',
      currency,
      tax_basis_points: Math.round((Number(taxPct) || 0) * 100),
      discount_basis_points: Math.round((Number(discountPct) || 0) * 100),
      quote_date: quoteDate || null,
      valid_until: validUntil || null,
      notes,
      terms,
      lines: usable.map((line) => ({
        description: line.description.trim(),
        quantity: String(Number(line.quantity) || 0),
        unit: line.unit.trim() || 'each',
        unit_price_cents: cents(line.price),
        discount_basis_points: Math.round((Number(line.discount) || 0) * 100),
      })),
      version: editing?.version ?? 1,
    };
    try {
      const saved = editing
        ? await api('/owner/crm/quotations/' + editing.id, 'PUT', body) as Quote
        : await api('/owner/crm/quotations', 'POST', body) as Quote;
      setEditorOpen(false);
      setEditing(null);
      await load();
      setStatus(editing
        ? 'Quotation saved. ' + (saved.reference ? saved.reference + ' · ' : '') + 'version ' + saved.version + '.'
        : 'Draft ' + (saved.reference || '') + ' saved. Preview it, then approve and send.');
      if (thenReview) setPendingSignoff(saved);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the quotation'); }
    setBusy(false);
  }

  async function signOff(quote: Quote) {
    setBusy(true);
    try {
      await api('/owner/crm/quotations/' + quote.id + '/status', 'POST', {status: 'reviewed', version: quote.version});
      setStatus('Approved. ' + (quote.reference || 'The quotation') + ' is ready to send.');
      setPendingSignoff(null);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not approve that quotation'); }
    setBusy(false);
  }

  async function voidQuote(quote: Quote) {
    setBusy(true);
    try {
      await api('/owner/crm/quotations/' + quote.id + '/status', 'POST', {status: 'void', version: quote.version});
      setStatus((quote.reference || 'That quotation') + ' is void. It is kept for the record.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not void that quotation'); }
    setBusy(false);
  }

  async function duplicateQuote(quote: Quote) {
    setBusy(true);
    try {
      const copy = await api('/owner/crm/quotations/' + quote.id + '/duplicate', 'POST', {}) as Quote;
      await load();
      setStatus('Copied to ' + (copy.reference || 'a new draft') + '. Edit it and send when ready.');
      openEdit(copy);
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not copy that quotation'); }
    setBusy(false);
  }

  async function preview(quote: Quote) {
    const response = await fetch('/owner/crm/quotations/' + quote.id + '/print', {headers: {Authorization: 'Bearer ' + token}});
    if (!response.ok) { setStatus('Could not prepare the document.'); return; }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  function openSend(quote: Quote) {
    setSendFor(quote);
    setSendSubject('Quotation ' + (quote.reference ? quote.reference + ' — ' : '') + quote.title);
    setSendMessage('');
  }

  async function send() {
    if (!sendFor) return;
    setBusy(true);
    try {
      const result = await api('/owner/crm/quotations/' + sendFor.id + '/send', 'POST',
        {subject: sendSubject, message: sendMessage}) as {sent_to: string; link: string};
      setStatus('Sent to ' + result.sent_to + '. You will see when they open it. Customer link: ' + result.link);
      setSendFor(null);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not send the quotation'); }
    setBusy(false);
  }

  async function copyLink(quote: Quote) {
    if (!quote.public_token) return;
    const link = window.location.origin + '/quote/' + quote.public_token;
    try { await navigator.clipboard.writeText(link); setStatus('Customer link copied: ' + link); }
    catch { setStatus('Customer link: ' + link); }
  }

  async function confirmPayment(id: string, action: 'confirm' | 'waive') {
    try {
      await api('/owner/crm/quotations/' + id + '/payment', 'POST', {action});
      setStatus(action === 'waive' ? 'Marked as no payment due.' : 'Payment confirmed.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not update that quotation'); }
  }

  async function savePaymentSettings() {
    try {
      await api('/owner/payment-settings', 'PUT', {instructions: pay.instructions || '', url: pay.url || ''});
      setStatus('Payment details saved. Accepted quotations show them to the customer.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save payment details'); }
  }

  async function saveBusiness() {
    try {
      await api('/owner/business', 'PUT', {
        name: biz.name || '', gst_number: biz.gst_number || '', nzbn: biz.nzbn || '',
        business_address: biz.business_address || '', business_phone: biz.business_phone || '',
        quote_terms: biz.quote_terms || '', quote_valid_days: Number(biz.quote_valid_days) || 30,
        allow_deposit: biz.allow_deposit !== false, deposit_percent: Number(biz.deposit_percent) || 0,
        invoice_payment_terms_days: Number(biz.invoice_payment_terms_days) || 7,
      });
      setStatus('Business details saved. New quotations print them, with a reference and a valid-until date.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save business details'); }
  }

  return (
    <VStack gap={5}>
      <HStack justify="between" align="center" style={{flexWrap: 'wrap'}} gap={3}>
        <VStack gap={1}>
          <Text type="supporting">{quotes.length} on file · {money(openValue, 'NZD')} awaiting a decision · {money(wonValue, 'NZD')} accepted</Text>
        </VStack>
        <HStack gap={2} align="center" style={{flexWrap: 'wrap'}}>
          <Button label="Quote from a plan or 3D model" variant="secondary" onClick={() => onOpenDesigns?.()} />
          <Button label="New quotation" variant="primary" onClick={openNew} />
        </HStack>
      </HStack>

      {quotes.length ? (
        <Card padding={0}>
          <Table
            data={quotes as unknown as Record<string, unknown>[]}
            idKey="id"
            density="compact"
            columns={[
              {key: 'reference', header: 'Quote', width: proportional(2, {minWidth: 170}), renderCell: (row) => (
                <VStack gap={1}>
                  <Text weight="semibold">{String(row.reference || '—')}</Text>
                  <Text type="supporting" size="sm">{String(row.title || '')}</Text>
                </VStack>
              )},
              {key: 'customer', header: 'Customer', width: proportional(2, {minWidth: 160}), renderCell: (row) => {
                const contact = (row.contact || {}) as Contact;
                return <VStack gap={1}>
                  <Text weight="medium">{contact.name || contact.email || contact.phone || 'Customer'}</Text>
                  {contact.company ? <Text type="supporting" size="sm">{contact.company}</Text> : null}
                </VStack>;
              }},
              {key: 'valid_until', header: 'Dates', width: proportional(2, {minWidth: 150}), renderCell: (row) => {
                const value = iso(String(row.valid_until || ''));
                const issued = iso(String(row.quote_date || row.created_at || ''));
                const expired = Boolean(value) && value! < today() && ['reviewed', 'sent', 'draft'].includes(String(row.status));
                return <VStack gap={1}>
                  <Text type="supporting" size="sm">issued {issued || '—'}</Text>
                  <HStack gap={1} align="center">
                    <Text type="supporting" size="sm">until {value || '—'}</Text>
                    {expired ? <Badge label="expired" variant="warning" /> : null}
                  </HStack>
                </VStack>;
              }},
              {key: 'status', header: 'Status', width: proportional(2, {minWidth: 140}), renderCell: (row) => (
                <HStack gap={1} align="center" style={{flexWrap: 'wrap'}}>
                  <Badge label={STATUS_LABEL[String(row.status)] || String(row.status)} variant={statusVariant(String(row.status))} />
                  {row.status === 'accepted' ? (
                    <Badge label={String(row.payment_status || 'unpaid')} variant={row.payment_status === 'paid' ? 'success' : row.payment_status === 'declared' ? 'info' : 'neutral'} />
                  ) : row.viewed_at && ['sent', 'reviewed'].includes(String(row.status)) ? <Badge label="opened" variant="neutral" /> : null}
                </HStack>
              )},
              {key: 'total_cents', header: 'Total', width: proportional(1, {minWidth: 110}), renderCell: (row) => (
                <Text weight="semibold">{money(Number(row.total_cents), String(row.currency || 'NZD'))}</Text>
              )},
              {key: 'id', header: '', width: proportional(2, {minWidth: 210}), renderCell: (row) => {
                const quote = row as unknown as Quote;
                const primary = quote.status === 'draft' ? {label: 'Edit', run: () => openEdit(quote)}
                  : quote.status === 'reviewed' ? {label: 'Send', run: () => openSend(quote)}
                  : quote.status === 'sent' ? {label: 'Resend', run: () => openSend(quote)}
                  : {label: 'View', run: () => void preview(quote)};
                return <HStack gap={2} align="center">
                  <Button label={primary.label} variant="primary" isDisabled={busy} onClick={primary.run} />
                  <MoreMenu label={'More actions for ' + (quote.reference || quote.title)} items={[
                    {label: 'Preview the document', onClick: () => void preview(quote)},
                    {label: 'Copy the customer link', onClick: () => void copyLink(quote), isDisabled: !quote.public_token},
                    {label: 'Edit as a new draft', onClick: () => void duplicateQuote(quote)},
                    {label: 'Mark accepted (verbal yes)', onClick: () => void api('/owner/crm/quotations/' + quote.id + '/status', 'POST', {status: 'accepted', version: quote.version}).then(load).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not mark it accepted')),
                      isDisabled: !(role === 'owner' && ['reviewed', 'sent'].includes(quote.status))},
                    {label: 'Confirm payment received', onClick: () => void confirmPayment(quote.id, 'confirm'),
                      isDisabled: !(role === 'owner' && quote.status === 'accepted' && ['unpaid', 'declared'].includes(String(quote.payment_status || 'unpaid')))},
                    {label: 'Void this quotation', onClick: () => void voidQuote(quote), isDisabled: quote.status === 'void'},
                  ]} />
                </HStack>;
              }},
            ] as TableColumn<Record<string, unknown>>[]}
          />
        </Card>
      ) : (
        <Card>
          <EmptyState title="No quotations yet" description="Write your first quote — pick an enquiry or type in a walk-in customer, add lines from your catalogue, and send a branded document the customer can accept online."
                      actions={<Button label="New quotation" variant="primary" onClick={openNew} />} />
        </Card>
      )}

      <Card>
        <HStack justify="between" align="center" style={{flexWrap: 'wrap'}} gap={2}>
          <VStack gap={1}>
            <Heading level={2}>Your quoting details</Heading>
            <Text type="supporting">These print on every quote: who issued it, your GST and NZBN, the reference, how long the price holds, and your terms.</Text>
          </VStack>
          <Button label={showSettings ? 'Hide settings' : 'Edit business details'} variant="secondary" onClick={() => setShowSettings(!showSettings)} />
        </HStack>
        {showSettings ? (
          <VStack gap={3} style={{marginTop: 12}}>
            <Grid columns={{minWidth: 260}} gap={3}>
              <TextInput label="Trading name" value={biz.name || ''} onChange={(v) => setBiz({...biz, name: v})} />
              <TextInput label="GST number" value={biz.gst_number || ''} onChange={(v) => setBiz({...biz, gst_number: v})} />
              <TextInput label="NZBN (optional)" value={biz.nzbn || ''} onChange={(v) => setBiz({...biz, nzbn: v})} />
              <TextInput label="Address" value={biz.business_address || ''} onChange={(v) => setBiz({...biz, business_address: v})} />
              <TextInput label="Phone" value={biz.business_phone || ''} onChange={(v) => setBiz({...biz, business_phone: v})} />
              <NumberInput label="Quote valid for (days)" value={Number(biz.quote_valid_days ?? 30)} onChange={(v) => setBiz({...biz, quote_valid_days: v})} min={1} max={365} />
              <NumberInput label="Deposit %" value={Number(biz.deposit_percent ?? 50)} onChange={(v) => setBiz({...biz, deposit_percent: v})} min={0} max={100} />
              <NumberInput label="Invoice payment terms (days)" value={Number(biz.invoice_payment_terms_days ?? 7)} onChange={(v) => setBiz({...biz, invoice_payment_terms_days: v})} min={0} max={120} />
            </Grid>
            <CheckboxInput label="Offer a deposit option on quotes" value={biz.allow_deposit !== false} onChange={(v) => setBiz({...biz, allow_deposit: v})} />
            <TextArea label="Terms and conditions (copied onto each new quote)" value={biz.quote_terms || ''} onChange={(v) => setBiz({...biz, quote_terms: v})} rows={4} />
            <Divider />
            <Heading level={3}>Getting paid</Heading>
            <Text type="supporting">An accepted quote shows these details with an &ldquo;I have paid&rdquo; button. You confirm it once the money lands — no card processor, no fees.</Text>
            <TextArea label="Payment instructions (bank details, how to pay)" value={pay.instructions || ''} onChange={(v) => setPay({...pay, instructions: v})} rows={3} />
            <TextInput label="Payment link (optional, https://…)" value={pay.url || ''} onChange={(v) => setPay({...pay, url: v})} />
            {pay.summary ? (
              <Text>{money(Number(pay.summary.paid_cents || 0), 'NZD')} confirmed · {money(Number(pay.summary.declared_cents || 0), 'NZD')} claimed, awaiting you · {money(Number(pay.summary.outstanding_cents || 0), 'NZD')} outstanding</Text>
            ) : null}
            <HStack gap={2}>
              <Button label="Save business details" variant="primary" onClick={() => void saveBusiness()} />
              <Button label="Save payment details" variant="secondary" onClick={() => void savePaymentSettings()} />
            </HStack>
          </VStack>
        ) : null}
      </Card>

      <Dialog isOpen={editorOpen} onOpenChange={(open) => { if (!open) setEditorOpen(false); }} width={1000}>
        <VStack gap={4}>
          <HStack justify="between" align="center" style={{flexWrap: 'wrap'}}>
            <VStack gap={1}>
              <Heading level={2}>{editing ? 'Edit ' + (editing.reference || 'quotation') : 'New quotation'}</Heading>
              <Text type="supporting">Every figure below is shown to the customer. Nothing is sent until you approve it.</Text>
            </VStack>
            {editing ? <Badge label={'version ' + editing.version} /> : null}
          </HStack>

          <Grid columns={{minWidth: 220}} gap={3}>
            <Selector label="Existing enquiry (optional)" hasClear placeholder="Walk-in customer"
                      value={leadId} onChange={(value) => pickLead(value as string | null)}
                      options={leads.map((lead) => ({value: lead.id, label: (lead.name || lead.email || lead.phone || 'Enquiry') + ' · ' + lead.channel}))} />
            <TextInput label="Quote title" value={title} onChange={setTitle} placeholder="Workshop cladding, 12 Main Rd" />
            <DateInput label="Quote date" value={quoteDate as never} onChange={(v) => setQuoteDate(String(v || ''))} />
            <DateInput label="Price holds until" value={validUntil as never} onChange={(v) => setValidUntil(String(v || ''))} />
          </Grid>

          <Grid columns={{minWidth: 220}} gap={3}>
            <TextInput label="Customer name" value={customer.name || ''} onChange={(v) => setCustomer({...customer, name: v})} />
            <TextInput label="Company (optional)" value={customer.company || ''} onChange={(v) => setCustomer({...customer, company: v})} />
            <TextInput label="Email" value={customer.email || ''} onChange={(v) => setCustomer({...customer, email: v})} />
            <TextInput label="Phone" value={customer.phone || ''} onChange={(v) => setCustomer({...customer, phone: v})} />
          </Grid>
          <TextArea label="Site or postal address (optional)" value={customer.address || ''} onChange={(v) => setCustomer({...customer, address: v})} rows={2} />

          <Divider />
          <HStack justify="between" align="center" style={{flexWrap: 'wrap'}}>
            <Heading level={3}>Line items</Heading>
            <Selector label="Add from your catalogue" placeholder="Choose a product" value=""
                      onChange={(value) => { addProduct(value); }}
                      options={products.map((product) => ({value: product.id, label: product.name + ' — ' + money(product.sale_price_cents, currency)}))} />
          </HStack>

          <VStack gap={2}>
            <HStack gap={2} align="center">
              <Text type="supporting" size="sm" style={{flex: '3 1 200px'}}>Description</Text>
              <Text type="supporting" size="sm" style={{flex: '0 0 80px'}}>Qty</Text>
              <Text type="supporting" size="sm" style={{flex: '0 0 90px'}}>Unit</Text>
              <Text type="supporting" size="sm" style={{flex: '0 0 110px'}}>Unit price</Text>
              <Text type="supporting" size="sm" style={{flex: '0 0 80px'}}>Disc %</Text>
              <Text type="supporting" size="sm" style={{flex: '0 0 110px', textAlign: 'right'}}>Amount</Text>
              <span style={{flex: '0 0 32px'}} />
            </HStack>
            {lines.map((line, index) => {
              const amounts = lineTotals(line);
              return (
                <HStack key={line.key} gap={2} align="end" style={{flexWrap: 'wrap'}}>
                  <span style={{flex: '3 1 200px', minWidth: 140}}>
                    <TextInput label={'Description for line ' + (index + 1)} isLabelHidden value={line.description}
                               onChange={(v) => updateLine(index, {description: v})} placeholder="Supply and install…" />
                  </span>
                  <span style={{flex: '0 0 80px'}}>
                    <NumberInput label={'Quantity for line ' + (index + 1)} isLabelHidden value={Number(line.quantity) || 0}
                                 min={0} step={0.01} onChange={(v) => updateLine(index, {quantity: String(v ?? 0)})} />
                  </span>
                  <span style={{flex: '0 0 90px'}}>
                    <TextInput label={'Unit for line ' + (index + 1)} isLabelHidden value={line.unit}
                               onChange={(v) => updateLine(index, {unit: v})} placeholder="each" />
                  </span>
                  <span style={{flex: '0 0 110px'}}>
                    <NumberInput label={'Unit price for line ' + (index + 1)} isLabelHidden value={Number(line.price) || 0}
                                 min={0} step={0.01} onChange={(v) => updateLine(index, {price: String(v ?? 0)})} />
                  </span>
                  <span style={{flex: '0 0 80px'}}>
                    <NumberInput label={'Discount percent for line ' + (index + 1)} isLabelHidden value={Number(line.discount) || 0}
                                 min={0} max={100} step={0.5} onChange={(v) => updateLine(index, {discount: String(v ?? 0)})} />
                  </span>
                  <span style={{flex: '0 0 110px', textAlign: 'right', paddingBottom: 8}}>
                    <Text weight="semibold">{money(amounts.amount, currency)}</Text>
                  </span>
                  <span style={{flex: '0 0 32px', paddingBottom: 2}}>
                    <IconButton label={'Remove line ' + (index + 1)} icon={<span aria-hidden>×</span>} variant="ghost"
                                isDisabled={lines.length === 1} onClick={() => setLines(lines.filter((_, i) => i !== index))} />
                  </span>
                </HStack>
              );
            })}
            <HStack gap={2}>
              <Button label="Add another line" variant="secondary" onClick={() => setLines([...lines, blankLine()])} />
              <Button label={busy ? 'Drafting…' : 'Draft with AI'} variant="ghost" isDisabled={busy} onClick={() => void draftWithAi()} />
            </HStack>
            {draftNote ? <Text type="supporting">{draftNote}</Text> : null}
            <TextArea label="What is the job? (used only for the AI draft)" value={brief} onChange={setBrief} rows={2} />
          </VStack>

          <Divider />
          <Grid columns={{minWidth: 260}} gap={4}>
            <VStack gap={3}>
              <Heading level={3}>Discount and tax</Heading>
              <Grid columns={2} gap={3}>
                <NumberInput label="Job discount %" value={Number(discountPct) || 0} min={0} max={100} step={0.5}
                             onChange={(v) => setDiscountPct(String(v ?? 0))} />
                <NumberInput label="Tax / GST %" value={Number(taxPct) || 0} min={0} max={100} step={0.5}
                             onChange={(v) => setTaxPct(String(v ?? 0))} />
                <Selector label="Currency" value={currency} onChange={(v) => setCurrency(v)}
                          options={[{value: 'NZD', label: 'NZD — New Zealand dollar'}, {value: 'USD', label: 'USD — US dollar'},
                            {value: 'AUD', label: 'AUD — Australian dollar'}, {value: 'GBP', label: 'GBP — pound'},
                            {value: 'EUR', label: 'EUR — euro'}]} />
              </Grid>
              <TextArea label="Notes shown on the quote" value={notes} onChange={setNotes} rows={3}
                        placeholder="Excludes scaffold. Site access by 7am." />
              <TextArea label="Terms on this quote" value={terms} onChange={setTerms} rows={3}
                        placeholder={biz.quote_terms ? 'Leave blank to use your saved terms' : 'Payment terms, exclusions, validity…'} />
            </VStack>
            <Card variant="muted">
              <VStack gap={2}>
                <Heading level={3}>Summary</Heading>
                <HStack justify="between"><Text type="supporting">Subtotal</Text><Text>{money(live.subtotal, currency)}</Text></HStack>
                {live.discount ? <HStack justify="between"><Text type="supporting">Discount</Text><Text>−{money(live.discount, currency)}</Text></HStack> : null}
                <HStack justify="between"><Text type="supporting">{currency === 'NZD' ? 'GST' : 'Tax'} {Number(taxPct) || 0}%</Text><Text>{money(live.tax, currency)}</Text></HStack>
                <Divider />
                <HStack justify="between" align="center"><Text weight="semibold">Total</Text><Heading level={3}>{money(live.total, currency)}</Heading></HStack>
                <Text type="supporting" size="sm">The customer sees these figures, the reference and your terms on one page.</Text>
              </VStack>
            </Card>
          </Grid>

          <Divider />
          <HStack justify="between" align="center" style={{flexWrap: 'wrap'}}>
            <Text type="supporting" size="sm">Saving keeps it as a draft. You approve it before it can be sent.</Text>
            <HStack gap={2}>
              <Button label="Cancel" variant="ghost" onClick={() => setEditorOpen(false)} />
              <Button label={busy ? 'Saving…' : 'Save draft'} variant="primary" isDisabled={busy} onClick={() => void save(false)} />
              <Button label="Save and approve" variant="secondary" isDisabled={busy} onClick={() => void save(true)} />
            </HStack>
          </HStack>
        </VStack>
      </Dialog>

      <Dialog isOpen={Boolean(pendingSignoff)} onOpenChange={(open) => { if (!open) setPendingSignoff(null); }}>
        <VStack gap={3}>
          <Heading level={2}>Approve this quotation?</Heading>
          <Text>{pendingSignoff?.reference} · {pendingSignoff?.title} · {pendingSignoff ? money(pendingSignoff.total_cents, pendingSignoff.currency) : ''}</Text>
          <Text type="supporting">Approving means you have checked every line, price and term. Once approved it can be sent, and the customer can accept it online.</Text>
          <HStack gap={2}>
            <Button label="Approve" variant="primary" isDisabled={busy} onClick={() => { if (pendingSignoff) void signOff(pendingSignoff); }} />
            <Button label="Preview first" variant="secondary" onClick={() => { if (pendingSignoff) void preview(pendingSignoff); }} />
            <Button label="Cancel" variant="ghost" onClick={() => setPendingSignoff(null)} />
          </HStack>
        </VStack>
      </Dialog>

      <Dialog isOpen={Boolean(sendFor)} onOpenChange={(open) => { if (!open) setSendFor(null); }}>
        <VStack gap={3}>
          <Heading level={2}>Send the quotation</Heading>
          <Text type="supporting">To {sendFor?.contact?.email || 'no email address'} — the customer gets the link, and you will see when they open it.</Text>
          <TextInput label="Subject" value={sendSubject} onChange={setSendSubject} />
          <TextArea label="Message (optional)" value={sendMessage} onChange={setSendMessage} rows={3}
                    placeholder="Kia ora Conrad — here is the clad quote we discussed." />
          <HStack gap={2}>
            <Button label={busy ? 'Sending…' : 'Send it'} variant="primary" isDisabled={busy || !sendFor?.contact?.email} onClick={() => void send()} />
            <Button label="Cancel" variant="ghost" onClick={() => setSendFor(null)} />
          </HStack>
          {!sendFor?.contact?.email ? <Text type="supporting">This quote has no email address. Edit the quote and add one first.</Text> : null}
        </VStack>
      </Dialog>

      <StatusLine text={status} />
    </VStack>
  );
}
