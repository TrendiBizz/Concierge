//! Quote-guard: a reply may state a dollar amount only if the evidence also contains it.
use regex::Regex;
use std::collections::BTreeSet;
use std::sync::OnceLock;

pub const FALLBACK: &str = "I don't have exact pricing on hand, and I don't want to guess. I can have the team confirm it for you - could I take your name and a phone number or email?";

pub const CORRECTION: &str = "Your previous answer contained a price that is not in the website information. Rewrite it without inventing any dollar amounts. If the exact price is not in the information, say you are not sure and offer to have the team confirm it (collect their contact details).";

fn amount_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?").unwrap())
}

/// A decimal amount compared by numeric value (so `$5`, `$5.00` and `$05.0` are equal), without floats.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct Amount {
    whole: String,
    frac: String,
}

impl Amount {
    /// Canonical text: no leading zeros, no trailing fractional zeros.
    pub fn canonical(&self) -> String {
        if self.frac.is_empty() {
            self.whole.clone()
        } else {
            format!("{}.{}", self.whole, self.frac)
        }
    }
}

pub fn amounts(text: &str) -> BTreeSet<Amount> {
    amount_re()
        .captures_iter(text)
        .map(|m| {
            let whole = m[1].replace(',', "");
            let whole = whole.trim_start_matches('0');
            let whole = if whole.is_empty() { "0" } else { whole };
            let frac = m.get(2).map_or("", |f| f.as_str()).trim_end_matches('0');
            Amount {
                whole: whole.to_string(),
                frac: frac.to_string(),
            }
        })
        .collect()
}

pub fn unknown_amounts(reply: &str, evidence: &str) -> BTreeSet<Amount> {
    let known = amounts(evidence);
    amounts(reply)
        .into_iter()
        .filter(|a| !known.contains(a))
        .collect()
}
