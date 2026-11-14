import {useEffect, useState} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Table, proportional} from '@astryxdesign/core/Table';
import type {TableColumn} from '@astryxdesign/core/Table';
import {TextInput} from '@astryxdesign/core/TextInput';
import {TextArea} from '@astryxdesign/core/TextArea';
import {MoreMenu} from '@astryxdesign/core/MoreMenu';
import {createApi as useApi} from './api';
import {StatusLine} from './StatusLine';

type Company = {id: string; name: string; domain?: string; notes?: string;
  contacts: number; open_deals: number; open_value_cents: number};

function money(cents: number) {
  return (Number(cents || 0) / 100).toLocaleString('en-NZ', {style: 'currency', currency: 'NZD'});
}

/**
 * Companies, so a business-to-business enquiry is not a stranded text field on one person.
 *
 * The value shown is the open pipeline attached to the company's people, which is the number a
 * salesperson actually wants: how much is on the table with this account.
 */
export function Companies({token}: {token: string}) {
  const api = useApi(token);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState('');

  async function load() {
    try { setCompanies(await api('/owner/companies') as Company[]); }
    catch (e) { setStatus(e instanceof Error ? e.message : 'Could not load companies'); }
  }
  useEffect(() => { load(); }, [token]);

  async function add() {
    if (!name.trim()) { setStatus('Give the company a name first.'); return; }
    try {
      await api('/owner/companies', 'POST', {name: name.trim(), domain: domain.trim(), notes: notes.trim()});
      setName(''); setDomain(''); setNotes('');
      setStatus('Added. You can now put people inside this company from Contacts.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not add that company'); }
  }

  async function remove(company: Company) {
    try {
      await api('/owner/companies/' + company.id, 'DELETE');
      setStatus('Deleted. Its people stay, they just are not in a company any more.');
      await load();
    } catch (e) { setStatus(e instanceof Error ? e.message : 'Could not delete that company'); }
  }

  return (
    <div>
      <p>
        One row per business you deal with, with how many of your people work there and how much
        is still open with them. Put a person inside a company from their card in Contacts.
      </p>
      <Card>
        <Heading level={2}>Add a company</Heading>
        <TextInput label="Company name" value={name} onChange={setName} placeholder="Pukeko Construction" />
        <TextInput label="Website (optional)" value={domain} onChange={setDomain} placeholder="pukekoconstruction.co.nz" />
        <TextArea label="Notes (optional)" value={notes} onChange={setNotes} />
        <Button label="Add company" variant="primary" onClick={() => void add()} />
      </Card>

      <Heading level={2}>Your companies</Heading>
      {companies.length ? (
        <Table
          data={companies as unknown as Record<string, unknown>[]}
          idKey="id"
          density="compact"
          columns={[
            {key: 'name', header: 'Company', width: proportional(2, {minWidth: 160}),
             renderCell: (row) => <strong>{String(row.name || '')}</strong>},
            {key: 'domain', header: 'Website', width: proportional(2, {minWidth: 150}),
             renderCell: (row) => String(row.domain || '—')},
            {key: 'contacts', header: 'People', width: proportional(1, {minWidth: 90}),
             renderCell: (row) => String(row.contacts ?? 0)},
            {key: 'open_deals', header: 'Open deals', width: proportional(1, {minWidth: 110}),
             renderCell: (row) => String(row.open_deals ?? 0)},
            {key: 'open_value_cents', header: 'Open value', width: proportional(1, {minWidth: 120}),
             renderCell: (row) => money(Number(row.open_value_cents || 0))},
            {key: 'id', header: '', width: proportional(1, {minWidth: 70}),
             renderCell: (row) => (
               <MoreMenu label={'More actions for ' + String(row.name || 'this company')} items={[
                 {label: 'Delete this company', onClick: () => void remove(row as unknown as Company)},
               ]} />
             )},
          ] as TableColumn<Record<string, unknown>>[]}
        />
      ) : (
        <p>No companies yet. Add the businesses you work with most, then put your contacts inside them.</p>
      )}
      <StatusLine text={status} />
    </div>
  );
}
