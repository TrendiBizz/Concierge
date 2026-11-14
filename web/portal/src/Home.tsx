import {useEffect, useState} from 'react';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid} from 'recharts';

type Brand = {name: string; accent: string};
type Lead = {id: string; name?: string; email?: string; channel: string; status: string};
type Quote = {status: string; total_cents: number};
type Post = {id: string};
type Asset = {id: string};

function useApi(token: string) {
  return async function api(path: string) {
    const response = await fetch(path, {headers: {Accept: 'application/json', Authorization: 'Bearer ' + token}, cache: 'no-store'});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'Request failed');
    return data;
  };
}

function money(cents: number, currency: string) {
  return new Intl.NumberFormat('en-NZ', {style: 'currency', currency}).format((cents || 0) / 100);
}

export default function Home({token, brand}: {token: string; brand: Brand}) {
  const api = useApi(token);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [posts, setPosts] = useState<Post[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [status, setStatus] = useState('');

  useEffect(() => {
    Promise.all([api('/owner/crm'), api('/owner/crm/quotations'), api('/owner/social/posts'), api('/owner/media/assets')])
      .then(([crm, q, p, a]) => {
        setLeads(((crm as {leads?: Lead[]}).leads || []));
        setQuotes(q as Quote[]); setPosts(p as Post[]); setAssets(a as Asset[]);
      }).catch((e) => setStatus(e instanceof Error ? e.message : 'Could not load the dashboard'));
  }, [token]);

  const quoted = quotes.filter((quote) => ['reviewed', 'accepted'].includes(quote.status)).reduce((sum, quote) => sum + quote.total_cents, 0);
  const channels = Object.entries(leads.reduce((acc, lead) => {
    acc[lead.channel] = (acc[lead.channel] || 0) + 1;
    return acc;
  }, {} as Record<string, number>)).map(([name, count]) => ({name, count}));
  const quoteStates = ['draft', 'reviewed', 'accepted', 'declined'].map((state) => ({name: state, count: quotes.filter((quote) => quote.status === state).length}));

  return (
    <div>
      <div className="c-kpis">
        {[['Enquiries', leads.length], ['Quoted value', money(quoted, 'NZD')], ['Posts', posts.length], ['Media', assets.length]].map(([label, value]) => (
          <div className="c-kpi" key={String(label)}><strong>{value}</strong><span>{label}</span></div>
        ))}
      </div>
      <div style={{display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', marginTop: 20}}>
        <Card>
          <Heading level={2}>Enquiries by channel</Heading>
          {channels.length === 0 ? <p style={{opacity: 0.7, fontSize: 14}}>Nothing yet. Each channel that sends you an enquiry will appear here.</p> : null}
          <div style={{height: 240}}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={channels}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill={brand.accent || '#c8f560'} radius={[4, 4, 0, 0]} /></BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <Heading level={2}>Quotations by status</Heading>
          {quotes.length === 0 ? <p style={{opacity: 0.7, fontSize: 14}}>No quotes yet. The first one you save will show up here as a draft.</p> : null}
          <div style={{height: 240}}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={quoteStates}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill={brand.accent || '#c8f560'} radius={[4, 4, 0, 0]} /></BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>
      <Heading level={2}>Latest enquiries</Heading>
      {leads.length === 0 ? (
        <div className="c-empty">
          <strong>No enquiries yet — and that is normal on day one.</strong>
          <p>Your chat window is ready. Once it is on your site (or you share your chat page), the
            first message a customer sends appears here, with their name and number already filled in.</p>
        </div>
      ) : null}
      {leads.slice(0, 5).map((lead) => (
        <div key={lead.id} className="c-row">
          <div className="c-row-avatar">{(lead.name || lead.email || 'E').slice(0, 1).toUpperCase()}</div>
          <div className="c-row-main">
            <strong>{lead.name || lead.email || 'Enquiry'}</strong>
            <span>{lead.channel || 'chat'} · {lead.status || 'new'}</span>
          </div>
          <span className="c-row-tag">{lead.status || 'new'}</span>
        </div>
      ))}
      {status ? <p role="status">{status}</p> : null}
    </div>
  );
}
