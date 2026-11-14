import {Banner} from '@astryxdesign/core/Banner';

/**
 * One status line for the whole Studio.
 *
 * Every page used to write `<p role="status">{status}</p>`, so a success, an upload and a failure
 * all looked like the same grey sentence. This renders the design system's Banner and picks the
 * tone from the wording the page already uses, so existing messages need no rewriting.
 */
const FAILED = /could not|failed|not supported|invalid|error|refused|unavailable|limit|expired|denied/i;
const WORKED = /saved|uploaded|deleted|made|added|posted|scheduled|sent|connected|invited|created|updated|copied|done|removed|cleared/i;

export function toneFor(text: string): 'info' | 'success' | 'error' {
  if (FAILED.test(text)) return 'error';
  if (WORKED.test(text)) return 'success';
  return 'info';
}

export function StatusLine({text, tone}: {text?: string | null; tone?: 'info' | 'success' | 'error' | 'warning'}) {
  const value = (text || '').trim();
  if (!value) return null;
  const status = tone ?? toneFor(value);
  return <Banner status={status} title={value} role={status === 'error' ? 'alert' : undefined} />;
}
