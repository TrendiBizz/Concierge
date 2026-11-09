//! Reactivation-campaign rules (port of the pure parts of `campaigns.py`).
use crate::py_strip;
use crate::unsub;
use serde_json::Value;

pub const STOP_LINE: &str = " Reply STOP to opt out.";
pub const CHANNELS: [&str; 2] = ["sms", "email"];
pub const LEAD_STATUSES: [&str; 5] = ["new", "contacted", "booked", "won", "lost"];
const PLACEHOLDERS: [&str; 2] = ["first", "business"];

// ---- CPython `string.Formatter().parse`, character for character ----------------------------------------------
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Field {
    pub name: String,
    pub conversion: Option<char>,
    pub spec: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Tok {
    Lit(String),
    Field(Field),
}

fn parse_field(c: &[char], i: &mut usize) -> Result<Field, String> {
    let name_start = *i;
    let mut ch = '\0';
    while *i < c.len() {
        ch = c[*i];
        *i += 1;
        match ch {
            '{' => return Err("unexpected '{' in field name".into()),
            '[' => {
                while *i < c.len() && c[*i] != ']' {
                    *i += 1;
                }
                continue;
            }
            '}' | ':' | '!' => break,
            _ => continue,
        }
    }
    let name_end = (*i).saturating_sub(1).max(name_start);
    let name: String = c[name_start..name_end.min(c.len())].iter().collect();
    let mut conversion = None;
    if ch == '!' || ch == ':' {
        if ch == '!' {
            if *i >= c.len() {
                return Err("end of string while looking for conversion specifier".into());
            }
            conversion = Some(c[*i]);
            *i += 1;
            if *i < c.len() {
                let next = c[*i];
                *i += 1;
                if next == '}' {
                    return Ok(Field {
                        name,
                        conversion,
                        spec: String::new(),
                    });
                }
                if next != ':' {
                    return Err("expected ':' after conversion specifier".into());
                }
            }
        }
        let spec_start = *i;
        let mut count = 1;
        while *i < c.len() {
            let x = c[*i];
            *i += 1;
            match x {
                '{' => count += 1,
                '}' => {
                    count -= 1;
                    if count == 0 {
                        return Ok(Field {
                            name,
                            conversion,
                            spec: c[spec_start..*i - 1].iter().collect(),
                        });
                    }
                }
                _ => {}
            }
        }
        return Err("unmatched '{' in format spec".into());
    } else if ch != '}' {
        return Err("expected '}' before end of string".into());
    }
    Ok(Field {
        name,
        conversion,
        spec: String::new(),
    })
}

pub fn tokenize(s: &str) -> Result<Vec<Tok>, String> {
    let c: Vec<char> = s.chars().collect();
    let mut i = 0;
    let mut out = Vec::new();
    while i < c.len() {
        let start = i;
        let mut ch = '\0';
        let mut markup = false;
        while i < c.len() {
            ch = c[i];
            i += 1;
            if ch == '{' || ch == '}' {
                markup = true;
                break;
            }
        }
        let at_end = i >= c.len();
        let mut len = i - start;
        if markup && ch == '}' && (at_end || c[i] != '}') {
            return Err("Single '}' encountered in format string".into());
        }
        if markup && at_end && ch == '{' {
            return Err("Single '{' encountered in format string".into());
        }
        let mut markup_follows = markup;
        if !at_end {
            if c[i] == ch {
                i += 1;
                markup_follows = false;
            } else {
                len -= 1;
            }
        }
        if len > 0 {
            out.push(Tok::Lit(c[start..start + len].iter().collect()));
        }
        if markup_follows {
            out.push(Tok::Field(parse_field(&c, &mut i)?));
        }
    }
    Ok(out)
}

/// `validate_template`; the error text is the `CampaignError` message.
pub fn validate_template(template: &str) -> Result<(), String> {
    if py_strip(template).is_empty() {
        return Err("Message body is empty".into());
    }
    if template.chars().count() > 600 {
        return Err("Message body is too long (600 characters max)".into());
    }
    let toks = tokenize(template).map_err(|e| format!("Bad placeholder syntax: {e}"))?;
    let bad = toks.iter().find_map(|t| match t {
        Tok::Field(f) if !PLACEHOLDERS.contains(&f.name.as_str()) => Some(f.name.clone()),
        _ => None,
    });
    if let Some(b) = bad {
        return Err(format!(
            "Unknown placeholder {{{b}}}. Allowed: {{first}}, {{business}}"
        ));
    }
    Ok(())
}

pub fn first_name(name: &str) -> String {
    let f = py_strip(name).split(' ').next().unwrap_or("");
    if f.is_empty() {
        "there".into()
    } else {
        f.into()
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum Render {
    Text(String),
    /// Python would render it, using a conversion or format spec this port does not reproduce.
    Unsupported,
    /// Python raises (unknown placeholder, bad syntax).
    Error,
}

/// `template.format(first=first_name(name), business=business)` for plain `{first}` / `{business}` fields.
pub fn render(template: &str, lead_name: &str, business: &str) -> Render {
    let Ok(toks) = tokenize(template) else {
        return Render::Error;
    };
    let first = first_name(lead_name);
    let mut out = String::new();
    for t in toks {
        match t {
            Tok::Lit(l) => out.push_str(&l),
            Tok::Field(f) => {
                let value = match f.name.as_str() {
                    "first" => &first,
                    "business" => business,
                    _ => return Render::Error,
                };
                // Python accepts only !s, !r and !a; anything else raises "Unknown conversion specifier".
                match f.conversion {
                    None | Some('s') => {}
                    Some('r') | Some('a') => return Render::Unsupported,
                    Some(_) => return Render::Error,
                }
                if !f.spec.is_empty() {
                    return Render::Unsupported;
                }
                out.push_str(value);
            }
        }
    }
    Render::Text(out)
}

pub fn email_footer(
    business: &str,
    notify_email: Option<&str>,
    tenant_id: &str,
    to_addr: &str,
    secret: &str,
    base: &str,
) -> Result<String, &'static str> {
    let mut lines = vec![
        String::new(),
        "--".to_string(),
        format!("You are receiving this because you contacted {business}."),
    ];
    if let Some(n) = notify_email.filter(|n| !n.is_empty()) {
        lines.push(format!("Contact: {n}"));
    }
    lines.push(format!(
        "Unsubscribe: {}",
        unsub::url_for(secret, base, tenant_id, to_addr)?
    ));
    Ok(lines.join("\n"))
}

pub fn mask(contact: &str) -> String {
    if let Some((local, domain)) = contact.split_once('@') {
        return format!("{}***@{domain}", local.chars().take(1).collect::<String>());
    }
    let chars: Vec<char> = contact.chars().collect();
    let head: String = chars.iter().take(3).collect();
    let tail: String = chars[chars.len().saturating_sub(3)..].iter().collect();
    format!(
        "{head}{}{tail}",
        "*".repeat(chars.len().saturating_sub(6).max(1))
    )
}

/// Spread `count` sends from `start_micros` at no more than `per_hour` per hour (microseconds since the epoch).
pub fn send_times(start_micros: i64, count: usize, per_hour: i64) -> Vec<i64> {
    let secs = 3600.0 / (per_hour.max(1) as f64);
    let whole = secs.trunc();
    let gap = (whole * 1e6) as i64 + ((secs - whole) * 1e6).round_ties_even() as i64;
    (0..count as i64).map(|i| start_micros + gap * i).collect()
}

#[derive(Debug, PartialEq, Eq)]
pub enum FilterError {
    Campaign(String),
    ValueError,
    TypeError,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Filters {
    pub statuses: Vec<String>,
    pub older_than_days: i64,
    pub min_score: i64,
    pub max_recipients: i64,
}

/// Python `int(x)` for JSON-derived values.
fn py_int(v: &Value) -> Result<i64, FilterError> {
    match v {
        Value::Bool(b) => Ok(*b as i64),
        Value::Number(n) => match n.as_i64() {
            Some(i) => Ok(i),
            None => n
                .as_f64()
                .filter(|f| f.is_finite())
                .map(|f| f.trunc() as i64)
                .ok_or(FilterError::ValueError),
        },
        Value::String(s) => {
            let t = py_strip(s);
            let digits = t.strip_prefix(['+', '-']).unwrap_or(t);
            if digits.is_empty() || !digits.chars().all(|c| c.is_ascii_digit()) {
                return Err(FilterError::ValueError);
            }
            t.parse().map_err(|_| FilterError::ValueError)
        }
        _ => Err(FilterError::TypeError),
    }
}

pub fn clean_filters(raw: &Value, settings_max_recipients: i64) -> Result<Filters, FilterError> {
    let statuses_v = match raw.get("statuses") {
        Some(v) if crate::pyval::truthy(Some(v)) => v.clone(),
        _ => serde_json::json!(["new", "contacted", "lost"]),
    };
    let msg = format!("statuses must be a list of: {}", LEAD_STATUSES.join(", "));
    let Value::Array(list) = &statuses_v else {
        return Err(FilterError::Campaign(msg));
    };
    let mut statuses = Vec::new();
    for item in list {
        match item {
            Value::Array(_) | Value::Object(_) => return Err(FilterError::TypeError),
            Value::String(s) if LEAD_STATUSES.contains(&s.as_str()) => statuses.push(s.clone()),
            _ => return Err(FilterError::Campaign(msg)),
        }
    }
    let older = py_int(raw.get("older_than_days").unwrap_or(&Value::from(30)))?;
    let min_score = py_int(raw.get("min_score").unwrap_or(&Value::from(0)))?;
    let cap = match raw.get("max_recipients") {
        None | Some(Value::Null) => settings_max_recipients,
        Some(v) => py_int(v)?,
    };
    if !(0..=3650).contains(&older) {
        return Err(FilterError::Campaign(
            "older_than_days must be 0-3650".into(),
        ));
    }
    if !(0..=100).contains(&min_score) {
        return Err(FilterError::Campaign("min_score must be 0-100".into()));
    }
    if cap < 1 {
        return Err(FilterError::Campaign(
            "max_recipients must be at least 1".into(),
        ));
    }
    Ok(Filters {
        statuses,
        older_than_days: older,
        min_score,
        max_recipients: cap.min(settings_max_recipients),
    })
}

/// `readiness`: reasons a campaign cannot be sent right now (empty = ready).
pub fn readiness(
    campaigns_enabled: bool,
    channel: &str,
    sms_enabled: bool,
    sms_sender_ready: bool,
    email_configured: bool,
    unsub_available: bool,
) -> Vec<&'static str> {
    let mut p = Vec::new();
    if !campaigns_enabled {
        p.push("Campaigns are switched off for this client (campaigns_enabled).");
    }
    if channel == "sms" {
        if !sms_enabled {
            p.push("Texting is not enabled for this client (sms_enabled).");
        }
        if !sms_sender_ready {
            p.push("No SMS provider is configured.");
        }
    } else {
        if !email_configured {
            p.push("Email (SMTP) is not configured.");
        }
        if !unsub_available {
            p.push("UNSUBSCRIBE_SECRET (or ADMIN_TOKEN) is not set, so unsubscribe links cannot be made.");
        }
    }
    p
}
