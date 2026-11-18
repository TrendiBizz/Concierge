"""Call-forwarding codes and number formats, driven entirely by data/call_forwarding.json."""
import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name('data') / 'call_forwarding.json'
ANSWER_MODES = ('all_calls', 'unanswered')


@lru_cache(maxsize=1)
def data() -> dict:
    return json.loads(DATA.read_text(encoding='utf-8'))


def countries() -> dict:
    return {k: v for k, v in data()['countries'].items() if not k.startswith('_')}


def normalize_country(code) -> str:
    code = str(code or '').strip().upper()
    return code if code in countries() else 'ZZ'


def normalize_carrier(carrier, country=None) -> str:
    """Unknown carriers become 'other'. With a country, a carrier of another country does too."""
    carrier = str(carrier or '').strip().lower()
    entry = data()['carriers'].get(carrier)
    if not entry or carrier == 'other':
        return 'other'
    if country and entry.get('country') and entry['country'] != country:
        return 'other'
    return carrier


def country_for_dial(dial_code) -> str | None:
    """The primary listed country for a calling code ('1' -> US), or None if unlisted."""
    dial_code = str(dial_code or '')
    matches = [(k, v) for k, v in countries().items() if v['dial'] == dial_code and dial_code]
    for k, v in matches:
        if v.get('primary'):
            return k
    return matches[0][0] if matches else None


def country_for_e164(e164: str) -> str | None:
    digits = str(e164 or '').lstrip('+')
    dials = {v['dial'] for v in countries().values() if v['dial'] and digits.startswith(v['dial'])}
    return country_for_dial(max(dials, key=len)) if dials else None


def tenant_dial_code(tenant: dict | None) -> str:
    """Dialling code from the tenant's own setting, then its timezone. Empty when unknown (never '1')."""
    tenant = tenant or {}
    own = str(tenant.get('default_country_code') or '').strip()
    if own.isdigit() and 1 <= len(own) <= 3:
        return own
    zone = str(tenant.get('timezone') or '')
    iso = data()['timezone_country'].get(zone)
    if not iso:
        iso = next((c for p, c in data()['timezone_prefix_country'].items() if zone.startswith(p)), None)
    return countries()[iso]['dial'] if iso else ''


def national_number(e164: str, country: str) -> str | None:
    """The number as dialled from inside `country`, or None if it belongs to a different calling code."""
    info = countries().get(country)
    digits = e164.lstrip('+')
    if not info or not info['dial'] or not digits.startswith(info['dial']):
        return None
    return info['trunk'] + digits[len(info['dial']):]


def dial_number(e164: str, country: str) -> str:
    """National format for the owner's own country, +E.164 for any other."""
    return national_number(e164, country) or e164


def is_cross_country(e164: str, country: str) -> bool:
    return national_number(e164, country) is None


def matches_destination(raw, e164: str, country: str) -> bool:
    """True when a number typed in any local or +E.164 form is the destination."""
    def digits(n):
        return ''.join(c for c in str(n or '') if c.isdigit())
    typed = digits(raw)
    national = national_number(e164, country)
    return bool(typed) and typed in {digits(e164), digits(national)}


def steps(destination: str, carrier: str, mode: str, country: str) -> dict:
    """{'set': [...], 'check': [...], 'cancel': [...], 'cancel_all': '##002#', 'note': ...}.

    Carrier overrides are merged per field over the GSM standard, so anything a carrier does not
    define falls back to the standard code.
    """
    d = data()
    mode = mode if mode in ANSWER_MODES else 'unanswered'
    carrier = normalize_carrier(carrier, country if country != 'ZZ' else None)
    entry = d['carriers'].get(carrier, {})
    kinds = entry.get('modes', {}).get(mode) or d['gsm']['modes'][mode]
    num = dial_number(destination, country)
    out = {'set': [], 'check': [], 'cancel': [], 'cancel_all': d['gsm']['cancel_all']}
    for kind in kinds:
        base = d['gsm']['kinds'][kind]
        over = entry.get('kinds', {}).get(kind, {})
        label = over.get('label') or base['label']
        for field in ('set', 'check', 'cancel'):
            code = over[field] if field in over else base[field]
            if code:
                out[field].append({'kind': kind, 'label': label, 'dial': code.replace('{num}', num)})
    notes = [entry['note']] if entry.get('note') else []
    if carrier == 'other' or not entry.get('verified'):
        notes.append('If a code does not work, ' + d['fallback_text'])
    out['note'] = ' '.join(notes)
    return out


def picker_lists() -> dict:
    cs = countries()
    carriers = data()['carriers']
    return {'countries': [
        {'code': k, 'name': v['name'], 'dial_code': v['dial'], 'international_prefix': v['intl_prefix'],
         'carriers': [{'id': 'other', 'name': carriers['other']['name']}] + [
             {'id': cid, 'name': c['name']} for cid, c in carriers.items() if c.get('country') == k]}
        for k, v in cs.items()]}


def device_hints() -> dict:
    return data()['devices']
