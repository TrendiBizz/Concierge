import {useEffect, useState} from 'react';
import {describeFailure} from './api';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {Badge} from '@astryxdesign/core/Badge';
import {Table, proportional} from '@astryxdesign/core/Table';
import type {TableColumn} from '@astryxdesign/core/Table';

type Product = {
  id: string;
  sku: string;
  name: string;
  description?: string;
  unit: string;
  sale_price_cents: number;
  cost_price_cents?: number | null;
  stock_quantity: number;
  active: boolean;
};

type Form = {
  id: string;
  sku: string;
  name: string;
  description: string;
  unit: string;
  price: string;
  cost: string;
  stock: string;
  active: boolean;
};

const EMPTY: Form = {id: '', sku: '', name: '', description: '', unit: 'each', price: '', cost: '', stock: '0', active: true};

function money(cents: number) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency: 'USD'}).format((cents || 0) / 100);
}

function dollars(value: string) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.round(number * 100) : 0;
}

export default function Products({token}: {token: string}) {
  async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {Accept: 'application/json', ...(body === undefined ? {} : {'Content-Type': 'application/json'}), Authorization: 'Bearer ' + token},
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
    return data;
  }

  const [products, setProducts] = useState<Product[]>([]);
  const [role, setRole] = useState('');
  const [form, setForm] = useState<Form>(EMPTY);
  const [adjust, setAdjust] = useState<Record<string, {delta: string; reason: string}>>({});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [p, me] = await Promise.all([api('/owner/products'), api('/owner/me')]);
      setProducts(p as Product[]);
      setRole((me as {role: string}).role);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not load products');
    }
  }
  useEffect(() => { load(); }, [token]);

  const isOwner = role === 'owner';

  function edit(product: Product) {
    setForm({
      id: product.id,
      sku: product.sku,
      name: product.name,
      description: product.description || '',
      unit: product.unit || 'each',
      price: (product.sale_price_cents / 100).toFixed(2),
      cost: product.cost_price_cents == null ? '' : (product.cost_price_cents / 100).toFixed(2),
      stock: String(product.stock_quantity),
      active: product.active,
    });
    setStatus('');
  }

  async function save() {
    setBusy(true); setStatus('');
    try {
      if (!form.sku.trim() || !form.name.trim()) throw new Error('SKU and name are required');
      const body = {
        sku: form.sku.trim(),
        name: form.name.trim(),
        description: form.description.trim(),
        unit: form.unit.trim() || 'each',
        sale_price_cents: dollars(form.price),
        cost_price_cents: form.cost.trim() === '' ? null : dollars(form.cost),
        stock_quantity: Math.round(Number(form.stock) || 0),
        active: form.active,
      };
      if (form.id) await api('/owner/products/' + form.id, 'PUT', body);
      else await api('/owner/products', 'POST', body);
      setStatus(form.id ? 'Product updated.' : 'Product added.');
      setForm(EMPTY);
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not save the product'); }
    setBusy(false);
  }

  async function stock(product: Product) {
    const entry = adjust[product.id] || {delta: '', reason: ''};
    setBusy(true); setStatus('');
    try {
      const delta = Math.round(Number(entry.delta));
      if (!Number.isFinite(delta) || delta === 0) throw new Error('Enter a non-zero stock change');
      await api('/owner/products/' + product.id + '/stock', 'POST', {delta, reason: entry.reason.trim()});
      setStatus(product.name + ': stock ' + (delta > 0 ? '+' : '') + delta + '.');
      setAdjust({...adjust, [product.id]: {delta: '', reason: ''}});
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not adjust stock'); }
    setBusy(false);
  }

  async function deactivate(product: Product) {
    setBusy(true); setStatus('');
    try {
      await api('/owner/products/' + product.id, 'DELETE');
      setStatus(product.name + ' deactivated. It stays in past quotations.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not deactivate the product'); }
    setBusy(false);
  }

  return (
    <div>
      <p>Your sale prices and stock. Quotes and the AI assistant can only use the sale price; cost price stays owner-only and is never shown to staff or customers.</p>
      {isOwner ? (
        <Card>
          <Heading level={2}>{form.id ? 'Edit product' : 'Add a product'}</Heading>
          <div style={{display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))'}}>
            <TextInput label="SKU" value={form.sku} onChange={(v) => setForm({...form, sku: v})} />
            <TextInput label="Name" value={form.name} onChange={(v) => setForm({...form, name: v})} />
            <TextInput label="Unit (each, m², hour)" value={form.unit} onChange={(v) => setForm({...form, unit: v})} />
            <TextInput label="Sale price" value={form.price} onChange={(v) => setForm({...form, price: v})} />
            <TextInput label="Cost price (owner only)" value={form.cost} onChange={(v) => setForm({...form, cost: v})} />
            <TextInput label="Stock quantity" value={form.stock} onChange={(v) => setForm({...form, stock: v})} />
          </div>
          <TextArea label="Description" value={form.description} onChange={(v) => setForm({...form, description: v})} rows={2} />
          <label style={{display: 'block', margin: '8px 0'}}>
            <input type="checkbox" checked={form.active} onChange={(e) => setForm({...form, active: e.target.checked})} /> Active (offer in quotes and chat)
          </label>
          <Button label={busy ? 'Saving…' : form.id ? 'Save changes' : 'Add product'} variant="primary" onClick={save} />
          {form.id ? <Button label="Cancel" variant="ghost" onClick={() => setForm(EMPTY)} /> : null}
        </Card>
      ) : (
        <p>You can adjust stock here. Prices and cost are managed by the business owner.</p>
      )}
      <Heading level={2}>Catalogue</Heading>
      <Table
        data={products as unknown as Record<string, unknown>[]}
        idKey="id"
        density="compact"
        columns={[
          {key: 'name', header: 'Product', width: proportional(2, {minWidth: 180}), renderCell: (row) => (
            <span><strong>{String(row.name || '')}</strong>{row.sku ? <span style={{opacity: 0.6}}> · {String(row.sku)}</span> : null}</span>
          )},
          {key: 'unit', header: 'Unit', width: proportional(1, {minWidth: 70}), renderCell: (row) => String(row.unit || 'each')},
          {key: 'sale_price_cents', header: 'Sale price', width: proportional(1, {minWidth: 100}), renderCell: (row) => money(Number(row.sale_price_cents))},
          ...(isOwner ? [{key: 'cost_price_cents', header: 'Cost', width: proportional(1, {minWidth: 90}), renderCell: (row: Record<string, unknown>) => row.cost_price_cents == null ? '—' : money(Number(row.cost_price_cents))}] : []),
          {key: 'stock_quantity', header: 'Stock', width: proportional(1, {minWidth: 70}), renderCell: (row) => String(row.stock_quantity ?? 0)},
          {key: 'active', header: 'Status', width: proportional(1, {minWidth: 90}), renderCell: (row) => <Badge label={row.active ? 'active' : 'inactive'} variant={row.active ? 'success' : 'neutral'} />},
          {key: 'id', header: 'Actions', width: proportional(1, {minWidth: 260}), renderCell: (row) => {
            const product = row as unknown as Product;
            const entry = adjust[product.id] || {delta: '', reason: ''};
            return (
              <span style={{display: 'inline-flex', gap: 4, flexWrap: 'wrap', alignItems: 'center'}}>
                <input aria-label={'Stock change for ' + product.name} placeholder="±qty" value={entry.delta}
                  onChange={(e) => setAdjust({...adjust, [product.id]: {...entry, delta: e.target.value}})}
                  style={{width: 64, padding: 6}} />
                <Button label="Adjust stock" variant="secondary" onClick={() => stock(product)} />
                {isOwner ? <Button label="Edit" variant="ghost" onClick={() => edit(product)} /> : null}
                {isOwner && product.active ? <Button label="Deactivate" variant="ghost" onClick={() => deactivate(product)} /> : null}
              </span>
            );
          }},
        ] as TableColumn<Record<string, unknown>>[]}
      />
      {!products.length ? <div className="c-empty"><strong>No products yet</strong><p>Add your first price — a product, a rate per square metre, or a fixed fee. Quotes and the chat window can only use numbers you have set.</p></div> : null}
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}
