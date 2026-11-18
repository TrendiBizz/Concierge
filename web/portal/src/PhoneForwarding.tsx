import {useEffect, useState} from 'react';
import type {ReactNode} from 'react';
import {Button} from '@astryxdesign/core/Button';
import {Card} from '@astryxdesign/core/Card';
import {Heading} from '@astryxdesign/core/Heading';
import {Banner} from '@astryxdesign/core/Banner';
import {Section} from '@astryxdesign/core/Section';
import {createApi} from './api';
import {copyText} from './clipboard';
import {useNotify} from './Notify';

type Code = {kind: string; label: string; dial: string};
type Carrier = {id: string; name: string};
type Country = {code: string; name: string; dial_code: string | null; international_prefix: string | null; carriers: Carrier[]};
type Connection = {
  status: 'destination_needed' | 'authorization_needed' | 'ready_to_forward' | 'call_received';
  destination: string | null;
  destination_display?: string;
  country: string;
  carrier: string;
  answer_mode: 'all_calls' | 'unanswered';
  country_mismatch?: boolean;
  destination_is_notify_phone?: boolean;
  destination_is_public_mobile?: boolean;
  notify_phone: string | null;
  steps: {set: Code[]; check: Code[]; cancel: Code[]; cancel_all: string; note?: string};
  countries: Country[];
  carriers: Carrier[];
  device_hints: Record<'iphone' | 'android', {label: string; path: string; note: string; tap_to_dial: boolean}>;
  last_call: {call_sid: string; status: string} | null;
};

const selectStyle = {display: 'block', width: '100%', marginTop: 6, padding: '10px 12px', borderRadius: 8, border: '1px solid var(--color-border)', background: 'transparent', fontSize: 14} as const;

/** iPhone blocks forwarding codes in tel: links, so only Android gets tap-to-dial. */
function phoneKind(): 'iphone' | 'android' | 'other' {
  const ua = navigator.userAgent || '';
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'iphone';
  return /Android/.test(ua) ? 'android' : 'other';
}

function CodeRow({code, tap}: {code: Code; tap: boolean}) {
  const notify = useNotify();
  const copy = () => { void copyText(code.dial).then((ok: boolean) => notify(ok ? 'Code copied.' : 'This browser blocked the clipboard — select the code and copy it.')); };
  return (
    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', padding: '8px 0'}}>
      <div>
        <div style={{fontSize: 13, opacity: 0.8}}>{code.label}</div>
        <code style={{fontSize: 18, wordBreak: 'break-all'}}>{code.dial}</code>
      </div>
      <div style={{display: 'flex', gap: 8}}>
        <Button label="Copy" variant="secondary" onClick={copy} />
        {tap ? <a href={'tel:' + code.dial.replace(/#/g, '%23')} style={{alignSelf: 'center', fontSize: 14}}>Tap to dial</a> : null}
      </div>
    </div>
  );
}

function CodeGroup({title, help, codes, tap}: {title: string; help: string; codes: Code[]; tap: boolean}) {
  if (!codes.length) return null;
  return (
    <div style={{marginTop: 16}}>
      <Heading level={3}>{title}</Heading>
      <p style={{fontSize: 14, margin: '4px 0'}}>{help}</p>
      {codes.map((code) => <CodeRow key={code.kind + code.dial} code={code} tap={tap} />)}
    </div>
  );
}

export function PhoneForwarding({token, consent, onContinue}: {token: string; consent: ReactNode; onContinue?: () => void}) {
  const api = createApi(token);
  const notify = useNotify();
  const [data, setData] = useState<Connection | null>(null);
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);
  const kind = phoneKind();

  const load = () => api('/owner/mobile-connection').then((d: Connection) => { setData(d); setProblem(''); }).catch((e: unknown) => setProblem(e instanceof Error ? e.message : 'Could not load this'));
  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [token]);

  async function save(change: {country?: string; carrier?: string; answer_mode?: string}) {
    setBusy(true);
    try { setData(await api('/owner/mobile-connection', 'PUT', change)); setProblem(''); }
    catch (e) { setProblem(e instanceof Error ? e.message : 'Could not save that'); }
    setBusy(false);
  }

  if (!data) return <Card><Heading level={2}>Phone: forward your calls</Heading><p>{problem || 'Loading…'}</p></Card>;

  const country = data.countries.find((c) => c.code === data.country);
  const hasNumber = data.status === 'ready_to_forward' || data.status === 'call_received';
  const tap = kind === 'android' && data.device_hints.android.tap_to_dial;
  const unanswered = data.answer_mode === 'unanswered';
  const number = data.destination_display || data.destination || '';

  return (
    <Card>
      <Section dividers={['top']}><Heading level={2}>Phone: forward your calls</Heading></Section>
      <p>Your own mobile number stays the same. You tell your phone to pass calls on to the number we give you, and Concierge answers them. This step is optional: you can finish setting up now and come back to it.</p>

      {data.status === 'call_received' ? (
        <Banner status="success" title="Your forwarding works" description="We received a call that was forwarded to your Concierge number. Remember to cancel forwarding if you only turned it on to test." />
      ) : data.status === 'ready_to_forward' ? (
        <Banner status="info" title="Your Concierge number is ready" description="Turn forwarding on from your phone using the codes below, then test it." />
      ) : data.status === 'authorization_needed' ? (
        <Banner status="warning" title="One thing first" description="Concierge needs your OK to answer calls before we show your number." />
      ) : (
        <Banner status="info" title="No number yet" description="When your phone line is set up we will give you a local number in your country. Come back to this step then — nothing else is blocked in the meantime." />
      )}

      {data.status === 'authorization_needed' ? (
        <div style={{marginTop: 12}}>
          {consent}
          <div style={{marginTop: 8}}><Button label="I have allowed it — check again" variant="secondary" onClick={() => { void load(); }} /></div>
        </div>
      ) : null}

      <div style={{display: 'grid', gap: 12, marginTop: 16}}>
        <label style={{fontSize: 14}}>Country of your mobile
          <select value={data.country} disabled={busy} onChange={(event) => { void save({country: event.target.value}); }} style={selectStyle}>
            {data.countries.map((c) => <option key={c.code} value={c.code}>{c.name}{c.dial_code ? ' (+' + c.dial_code + ')' : ''}</option>)}
          </select>
        </label>
        <label style={{fontSize: 14}}>Your mobile carrier
          <select value={data.carrier} disabled={busy} onChange={(event) => { void save({carrier: event.target.value}); }} style={selectStyle}>
            {data.carriers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <fieldset style={{border: '1px solid var(--color-border)', borderRadius: 8, padding: 12}}>
          <legend style={{fontSize: 14}}>Which calls should Concierge answer?</legend>
          <label style={{display: 'block', fontSize: 14, marginBottom: 6}}>
            <input type="radio" name="answer-mode" checked={unanswered} disabled={busy} onChange={() => { void save({answer_mode: 'unanswered'}); }} /> Ring me first — Concierge answers calls you miss, when you are busy, or when your phone has no signal
          </label>
          <label style={{display: 'block', fontSize: 14}}>
            <input type="radio" name="answer-mode" checked={!unanswered} disabled={busy} onChange={() => { void save({answer_mode: 'all_calls'}); }} /> All calls — Concierge answers every call
          </label>
        </fieldset>
      </div>

      {hasNumber ? (
        <>
          <div style={{marginTop: 20}}>
            <Heading level={3}>Your Concierge number</Heading>
            <div style={{display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap'}}>
              <code style={{fontSize: 22}}>{number}</code>
              <Button label="Copy" variant="secondary" onClick={() => { void copyText(number).then((ok: boolean) => notify(ok ? 'Number copied.' : 'This browser blocked the clipboard — select the number and copy it.')); }} />
            </div>
            <p style={{fontSize: 13, opacity: 0.75}}>Written the way you dial it from {country?.name || 'your country'}{data.country_mismatch ? ', with the country code because it is a number from another country' : ''}.</p>
          </div>

          {data.destination_is_notify_phone || data.destination_is_public_mobile ? (
            <Banner status="error" title="Do not forward to this number from itself" description="This number is the same as your own mobile or the number we send alerts to. Forwarding to it would loop calls back and forth. Stop and contact us." />
          ) : (
            <Banner status="warning" title="Never forward calls to your own mobile or the number we text alerts to" description="That would send calls round in a circle. Only use the Concierge number above." />
          )}
          {data.country_mismatch ? (
            <Banner status="warning" title="This number is from another country" description="Forwarding to it can cost more, and some carriers do not allow it. If it fails, ask us for a number in your country." />
          ) : null}

          <CodeGroup title="1. Turn forwarding on" codes={data.steps.set} tap={tap}
            help={kind === 'iphone'
              ? 'Open the Phone app, type the code on the keypad and press call. Do not use Messages, and tapping a code will not work on iPhone.'
              : tap ? 'Tap to dial, then press call. Or type it on your phone keypad.' : 'Type the code on your phone keypad in the Phone app and press call.'} />
          <CodeGroup title="Check it is on" codes={data.steps.check} tap={tap} help="Optional. Your phone shows what is set up." />
          <CodeGroup title="Turn forwarding off" codes={data.steps.cancel} tap={tap} help="Use these when you are finished testing, or any time you want calls to stop going to Concierge." />
          <div style={{marginTop: 8}}>
            <CodeRow code={{kind: 'cancel_all', label: 'Cancel all forwarding at once', dial: data.steps.cancel_all}} tap={tap} />
          </div>
          {data.steps.note ? <p style={{fontSize: 13, opacity: 0.8}}>{data.steps.note}</p> : null}

          <div style={{marginTop: 16}}>
            <Heading level={3}>Or use your phone's settings</Heading>
            {kind !== 'android' ? <p style={{fontSize: 14}}><strong>{data.device_hints.iphone.label}:</strong> {data.device_hints.iphone.path}. {data.device_hints.iphone.note}</p> : null}
            {kind !== 'iphone' ? <p style={{fontSize: 14}}><strong>{data.device_hints.android.label}:</strong> {data.device_hints.android.path}. {data.device_hints.android.note}</p> : null}
          </div>

          <div style={{marginTop: 16}}>
            <Heading level={3}>2. Test it</Heading>
            <p style={{fontSize: 14}}>Call your mobile from another phone.{' '}
              {unanswered
                ? 'Let it ring without answering (or decline it). After a few rings Concierge should pick up.'
                : 'Concierge should answer straight away, without your phone ringing.'}</p>
            <p style={{fontSize: 14}}>When it works this page says "Your forwarding works". <Button label="Check for the call" variant="secondary" onClick={() => { void load(); }} /></p>
            <p style={{fontSize: 14}}><strong>After testing,</strong> turn forwarding off with the codes above if you do not want Concierge answering yet.</p>
          </div>
        </>
      ) : data.status === 'destination_needed' ? (
        <p style={{fontSize: 14, marginTop: 16}}>We will assign you a local number{country && country.code !== 'ZZ' ? ' in ' + country.name : ''} when your line is bought. The codes to type will appear here then.</p>
      ) : null}

      {problem ? <p role="alert" className="error-note"><strong>Problem:</strong> {problem}</p> : null}
      {onContinue ? <div style={{marginTop: 16}}><Button label="Continue" variant="primary" onClick={onContinue} /></div> : null}
    </Card>
  );
}
