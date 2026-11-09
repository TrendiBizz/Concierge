//! Quotation money arithmetic (port of `quotations.calculate` and its validation). Integer minor units only;
//! half-up rounding on exact scaled integers, never floats.
use serde_json::{json, Value};

pub const MAX_TOTAL_CENTS: i128 = 100_000_000_000;

/// Outcome of parsing a quantity string.
#[derive(Debug, PartialEq, Eq)]
pub enum Quantity {
    /// Canonical text (as Python's `str(Decimal)`) and the value in thousandths.
    Valid { text: String, milli: i128 },
    /// Python rejects it.
    Invalid,
    /// A form Python accepts (exponent, underscores) that this port deliberately does not handle yet.
    Unsupported,
}

/// Parse a decimal quantity: `gt 0`, `le 100000`, at most 3 decimal places (trailing zeros don't count).
pub fn parse_quantity(raw: &str) -> Quantity {
    let s = crate::py_strip(raw);
    if s.contains(['e', 'E', '_']) {
        return if s.contains('_') || s.contains(['e', 'E']) {
            Quantity::Unsupported
        } else {
            Quantity::Invalid
        };
    }
    let (neg, body) = match s.strip_prefix('-') {
        Some(r) => (true, r),
        None => (false, s.strip_prefix('+').unwrap_or(s)),
    };
    let (int_part, frac_part) = body.split_once('.').unwrap_or((body, ""));
    let ok = |p: &str| p.chars().all(|c| c.is_ascii_digit());
    if (int_part.is_empty() && frac_part.is_empty()) || !ok(int_part) || !ok(frac_part) {
        return Quantity::Invalid;
    }
    let int_trim = int_part.trim_start_matches('0');
    let int_text = if int_trim.is_empty() { "0" } else { int_trim };
    let significant_frac = frac_part.trim_end_matches('0');
    if significant_frac.len() > 3 || neg {
        return Quantity::Invalid;
    }
    let mut milli: i128 = int_text.parse().unwrap_or(i128::MAX);
    if milli > 100_000 {
        return Quantity::Invalid;
    }
    milli *= 1000;
    let mut f = significant_frac.to_string();
    while f.len() < 3 {
        f.push('0');
    }
    milli += f.parse::<i128>().unwrap_or(0);
    if milli <= 0 || milli > 100_000_000 {
        return Quantity::Invalid;
    }
    let text = if frac_part.is_empty() {
        int_text.to_string()
    } else {
        format!("{int_text}.{frac_part}")
    };
    Quantity::Valid { text, milli }
}

pub struct Line {
    pub description: String,
    pub quantity: String,
    pub unit_price_cents: i64,
}

pub struct Calculated {
    pub lines: Vec<Value>,
    pub subtotal: i128,
    pub tax: i128,
    pub total: i128,
}

fn half_up(numerator: i128, denominator: i128) -> i128 {
    (numerator * 2 + denominator) / (denominator * 2)
}

/// Validate each line and compute amounts, subtotal, tax and total. `Err` carries the user-facing message.
pub fn calculate(lines: &[Line], tax_basis_points: i64) -> Result<Calculated, String> {
    let mut out = Vec::new();
    let mut subtotal: i128 = 0;
    for l in lines {
        let desc = crate::py_strip(&l.description);
        if l.description.chars().count() == 0
            || l.description.chars().count() > 300
            || desc.is_empty()
            || l.description.chars().any(|c| (c as u32) < 32)
        {
            return Err("Enter a readable line description".into());
        }
        if !(0..=100_000_000).contains(&l.unit_price_cents) {
            return Err("unit_price_cents out of range".into());
        }
        let Quantity::Valid { text, milli } = parse_quantity(&l.quantity) else {
            return Err("quantity invalid or unsupported".into());
        };
        let amount = half_up(milli * l.unit_price_cents as i128, 1000);
        subtotal += amount;
        out.push(json!({"description": desc, "quantity": text, "unit_price_cents": l.unit_price_cents, "amount_cents": amount as i64}));
    }
    if !(0..=10_000).contains(&tax_basis_points) {
        return Err("tax_basis_points out of range".into());
    }
    let tax = half_up(subtotal * tax_basis_points as i128, 10_000);
    if subtotal + tax > MAX_TOTAL_CENTS {
        return Err("Quotation total exceeds supported amount".into());
    }
    Ok(Calculated {
        lines: out,
        subtotal,
        tax,
        total: subtotal + tax,
    })
}

/// Statuses a quotation may move *from* to reach `to` (`quotations.change_status`).
pub fn allowed_from(to: &str) -> Option<&'static [&'static str]> {
    Some(match to {
        "reviewed" => &["draft"],
        "accepted" | "declined" => &["reviewed"],
        "void" => &["draft", "reviewed", "accepted", "declined"],
        _ => return None,
    })
}
