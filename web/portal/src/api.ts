/**
 * One fetch helper for the whole Studio.
 *
 * Every page used to carry its own copy, each with slightly different error handling. That is how
 * "The origin web server returned an invalid or incomplete response to Cloudflare" ended up printed
 * at a customer on the Media page: the fix landed in one copy and the other five kept the raw text.
 * Anything user-facing about a failed request belongs here, once.
 */

const EDGE_STATUSES = [502, 504, 520, 521, 522, 523, 524];

/** Turn any failed response into a sentence a tradesperson can act on. */
export function describeFailure(status: number, payload: unknown): string {
  const detail = typeof (payload as {detail?: unknown})?.detail === 'string'
    ? (payload as {detail: string}).detail
    : Array.isArray((payload as {detail?: unknown})?.detail)
      ? ((payload as {detail: Array<{msg?: string}>}).detail).map((d) => d.msg || 'A detail is not valid.').join(' ')
      : '';
  if (detail) return detail;
  if (EDGE_STATUSES.includes(status)) {
    return 'That took too long at our end (' + status + '). Nothing was lost — try again.';
  }
  if (status === 401) return 'Your session has expired. Sign in again.';
  if (status === 403) return 'You do not have permission to do that.';
  if (status === 404) return 'That is not here any more.';
  return 'Request failed (' + status + '). Try again.';
}

export function createApi(token: string) {
  return async function api(path: string, method = 'GET', body?: unknown) {
    const response = await fetch(path, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body !== undefined ? {'Content-Type': 'application/json'} : {}),
        ...(token ? {Authorization: 'Bearer ' + token} : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
    const raw = await response.text();
    // An edge failure (Cloudflare 520/524) is HTML, not JSON. Never show that to a customer.
    let data: any = {};
    try { data = raw ? JSON.parse(raw) : {}; } catch { data = {}; }
    if (response.status === 401 && token) window.dispatchEvent(new Event('concierge:sign-out'));
    if (!response.ok) throw new Error(describeFailure(response.status, data));
    return data;
  };
}
