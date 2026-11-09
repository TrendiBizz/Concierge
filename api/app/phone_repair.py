"""Repair phone numbers written by the old normaliser.

`normalize_phone` was fixed, but that fixes INPUT only. Values already in the database were written
by the buggy version and the new function cannot repair them, because a stored value is treated as
already-decisive: '+021555123' starts with '+', so it passes straight through, and '+646421555123'
stays doubled. Running the new normaliser over the database is therefore a no-op, which is why this
module exists separately.

The three damaged shapes the old code could write, all of them undialable or wrong:

  1. a kept national trunk prefix      '021555123'      -> should be '+6421555123'
  2. a kept trunk prefix after a '+'   '+021555123'     -> should be '+6421555123'
  3. a doubled country code            '+646421555123'  -> should be '+6421555123'

Anything else is left EXACTLY as-is. In particular a value that is already a clean E.164 number must
not be touched, and a value we cannot confidently repair must be reported rather than guessed at --
rewriting a customer's number wrongly is worse than leaving it, because it silently sends messages
to a stranger.

Every repair is tenant-aware: the trunk prefix and the country code are the TENANT's, so the same
stored string can legitimately repair differently for two businesses.
"""
from __future__ import annotations

import re

from .contact import DIAL_PLANS, MIN_E164_DIGITS, MAX_E164_DIGITS

# Columns holding a customer-visible number, with the tenant link used to resolve the country code.
# `opt_outs.contact` and `outbox.to_addr` may hold an EMAIL as well as a number, so they need the
# "leave non-phone contact values alone" path.
# (table, column, tenant column, key column). The key is used to scope each UPDATE to one row.
# `opt_outs` has NO `id`: its primary key is (tenant_id, contact), so it is repaired by its key and
# needs the merge path below because a repair can collide with an existing row for the same person.
PHONE_TARGETS = (
    ("leads", "phone", "tenant_id", "id"),
    ("appointments", "phone", "tenant_id", "id"),
    ("outbox", "to_addr", "tenant_id", "id"),
    ("opt_outs", "contact", "tenant_id", None),   # composite key; repaired separately
)

_LONE_TRUNK_CC = re.compile(r"^\+(\d{1,3})(0)(\d+)$")


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def repair_phone(raw: str, cc: str) -> tuple[str, str]:
    """Return (repaired_value, reason). `reason` is '' when nothing changed.

    Repairs only the three damaged shapes. Anything unrecognised is returned unchanged with an empty
    reason, so a caller can count it as "left alone" rather than "fixed".
    """
    value = (raw or "").strip()
    if not value:
        return raw, ""

    # An email is a legitimate value in some of these columns. Never touch it. This check is
    # LOAD-BEARING: an address can carry digits that form a valid national number, in which case a
    # repair without it rewrites the address as somebody's phone number.
    if "@" in value:
        return raw, ""

    plan = DIAL_PLANS.get(cc)
    if plan is None:
        return raw, ""  # no dial plan means no basis for a repair
    trunk = plan["trunk"]
    lengths = plan["national_lengths"]

    digits = _digits(value)
    if not digits:
        return raw, ""
    had_plus = value.startswith("+")

    # ---- already clean: an international number of a plausible length is left alone.
    if had_plus and len(digits) > len(cc) and digits.startswith(cc):
        rest = digits[len(cc):]
        if rest and not (trunk and rest.startswith(trunk)) and len(rest) in lengths:
            return raw, ""
        # A doubled country code: '+646421555123' -- the cc repeated.
        if rest.startswith(cc) and len(rest) > len(cc):
            inner = rest[len(cc):]
            if len(inner) in lengths:
                return f"+{cc}{inner}", "doubled country code removed"

    # ---- shape 2: a trunk prefix kept after a '+'
    if had_plus and trunk:
        match = _LONE_TRUNK_CC.match(value.replace(" ", ""))
        if match and match.group(1) == cc and len(match.group(3)) in lengths:
            return f"+{cc}{match.group(3)}", "trunk prefix removed after +"

    # ---- shape 3: a doubled country code with no '+' ('646421555123')
    if not had_plus and digits.startswith(cc):
        rest = digits[len(cc):]
        if rest.startswith(cc) and len(rest) > len(cc):
            inner = rest[len(cc):]
            if len(inner) in lengths:
                return f"+{cc}{inner}", "doubled country code removed"

    # ---- shape 1: a plain national number whose trunk prefix was kept
    if trunk and digits.startswith(trunk) and len(digits) > 1:
        stripped = digits[len(trunk):]
        if len(stripped) in lengths:
            return f"+{cc}{stripped}", "trunk prefix removed"

    # ---- shape 4: a complete national number stored without a '+' and without its trunk.
    # e.g. a US '2145550100' (trunk '1', 10 digits). The old code's 10-digit branch stored it as
    # '+1' + digits for a +1 tenant, but for any other tenant it produced a wrong number, so these
    # need the tenant's code applied. Only when the length is an exact national length, so nothing
    # is guessed.
    if not had_plus and len(digits) in lengths:
        return f"+{cc}{digits}", "country code applied to a bare national number"

    return raw, ""


def repair_contact(raw: str, cc: str) -> tuple[str, str]:
    """Repair a value that may be an email, a phone number, or an unparseable contact.

    Email and unparseable values are returned unchanged. The distinction matters for opt-out rows:
    a contact we cannot parse must keep its original key, because that is what `contact_key` would
    have stored, and changing it would orphan the opt-out.
    """
    value = (raw or "").strip()
    if not value or "@" in value:
        return raw, ""
    repaired, reason = repair_phone(value, cc)
    if reason:
        return repaired, reason
    # Not one of the known-bad shapes. Only canonicalise when the result is a usable number.
    from .contact import normalize_phone

    normalised = normalize_phone(value, cc)
    if normalised and normalised != value:
        return normalised, "canonicalised"
    return raw, ""


def is_usable(value: str, cc: str) -> bool:
    """True when this stored value is something we could actually dial.

    A number is usable when it is in international form, is a plausible E.164 length, and does NOT
    still carry the tenant's national trunk prefix after the country code -- a kept trunk digit is
    exactly the damage this module repairs.
    """
    if not value or "@" in value:
        return True  # not a phone, so not a phone problem
    if not value.startswith("+"):
        return False  # not international form, so not dialable as stored
    digits = _digits(value)
    if not (MIN_E164_DIGITS <= len(digits) <= MAX_E164_DIGITS):
        return False
    if not digits.startswith(cc):
        # It does not begin with the tenant's country code. That is either a legitimately different
        # country (fine) or a value whose '+' was followed by a bare national number, which is the
        # trunk-prefix damage ('+021555123'). Distinguish by asking whether the repair would change
        # it: if it would, the stored value is not usable as-is.
        return repair_phone(value, cc)[1] == ""
    plan = DIAL_PLANS.get(cc) or {}
    trunk = plan.get("trunk")
    if trunk:
        # Slice from the country code, then check the next digit.
        after_cc = digits[len(cc):]
        if after_cc.startswith(trunk) and len(after_cc) > 1:
            # A kept trunk digit is only damage when what follows is itself a valid national number.
            if len(after_cc) - len(trunk) in plan.get("national_lengths", ()):
                return False
    return True


# ------------------------------------------------------------------ migration runner


async def survey(pool) -> dict:
    """Count what is damaged, changing nothing. Always safe to run.

    Reports per column: total rows, how many hold a phone, how many are broken, and how many are
    beyond confident repair. The last count matters: those are the values a human must look at,
    because guessing at them would send messages to a stranger.
    """
    from .casetimeline import tenant_country_code

    tenants = {r["id"]: dict(r) for r in await pool.fetch("SELECT * FROM tenants")}
    report: dict = {"columns": {}, "tenants": len(tenants)}

    for table, column, link, _key in PHONE_TARGETS:
        rows = await pool.fetch(f"SELECT {link} AS tid, {column} AS value FROM {table} "
                               f"WHERE {column} IS NOT NULL AND {column} <> ''")
        total = len(rows)
        phones = 0
        broken = 0
        unrepaired: list[str] = []
        for row in rows:
            value = row["value"] or ""
            if "@" in value:
                continue  # an email legitimately stored in this column
            phones += 1
            cc = tenant_country_code(tenants.get(row["tid"]))
            repaired, reason = repair_contact(value, cc)
            if repaired != value:
                broken += 1
            elif not is_usable(value, cc):
                unrepaired.append(value)
        report["columns"][f"{table}.{column}"] = {
            "rows": total, "phones": phones, "broken": broken,
            "needs_human": sorted(set(unrepaired)),
        }
    return report


async def migrate(pool, *, dry_run: bool = True) -> dict:
    """Repair every damaged phone value. Dry run by default.

    Each UPDATE is scoped by the row's tenant, so the trunk prefix and country code applied are the
    tenant's own. Emails and unrepairable values are left untouched. Returns per-column counts and
    the values that could not be repaired, which are reported rather than guessed at.
    """
    from .casetimeline import tenant_country_code

    tenants = {r["id"]: dict(r) for r in await pool.fetch("SELECT * FROM tenants")}
    result: dict = {"dry_run": dry_run, "changed": {}, "needs_human": {}}

    for table, column, link, key in PHONE_TARGETS:
        if key is None:
            continue  # composite-key table, handled by _merge_opt_out_repairs below
        rows = await pool.fetch(f"SELECT {key} AS row_key, {link} AS tid, {column} AS value FROM {table} "
                               f"WHERE {column} IS NOT NULL AND {column} <> ''")
        changed = 0
        unrepaired: list[str] = []
        for row in rows:
            value = row["value"] or ""
            if "@" in value:
                continue
            cc = tenant_country_code(tenants.get(row["tid"]))
            repaired, reason = repair_contact(value, cc)
            if not reason:
                if not is_usable(value, cc):
                    unrepaired.append(value)
                continue
            if not dry_run:
                # Scoped by id, which is unique within the table.
                await pool.execute(
                    f"UPDATE {table} SET {column} = $1 WHERE {key} = $2 AND {column} = $3",
                    repaired, row["row_key"], value)
            changed += 1
        result["changed"][f"{table}.{column}"] = changed
        result["needs_human"][f"{table}.{column}"] = sorted(set(unrepaired))

    # opt_outs has a composite key (tenant_id, contact) rather than an id, and a changed key can
    # collide with an existing row for the same person. Handle it explicitly so a repair merges
    # rather than failing.
    merged = await _merge_opt_out_repairs(pool, tenants, dry_run=dry_run)
    result["changed"]["opt_outs.contact"] = merged
    return result


async def _merge_opt_out_repairs(pool, tenants, *, dry_run: bool = False) -> int:
    """Repair opt-out keys, merging duplicates so an opt-out is never lost.

    `opt_outs` has no `id`: its key IS (tenant_id, contact). A repaired key can therefore collide
    with a row that already exists for the same person, which a plain UPDATE could not express.
    The insert-then-delete below makes the repaired key win in that case. Keeping only one of the
    two would leave a customer textable after unsubscribing, which is the failure this prevents.

    Counts what it would change when dry_run is set, and changes nothing.
    """
    from .casetimeline import tenant_country_code

    changed = 0
    rows = await pool.fetch("SELECT tenant_id, contact FROM opt_outs")
    for row in rows:
        value = row["contact"] or ""
        if "@" in value or not value:
            continue
        cc = tenant_country_code(tenants.get(row["tenant_id"]))
        repaired, reason = repair_contact(value, cc)
        if not reason or repaired == value:
            continue
        if dry_run:
            changed += 1
            continue
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO opt_outs (tenant_id, contact) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    row["tenant_id"], repaired)
                await conn.execute(
                    "DELETE FROM opt_outs WHERE tenant_id = $1 AND contact = $2",
                    row["tenant_id"], value)
        changed += 1
    return changed
