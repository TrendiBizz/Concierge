//! Port of the client report page in `main.py` (`_stats`, `_money` and `client_report`).
//!
//! The unguessable report token is the credential for `GET /report/{token}`; the page is read-only.
//! Everything here is a pure function of the tenant row and the aggregates, so the statement text can be
//! compared with the live Python without a database. The aggregation SQL itself lives in `concierge-server`,
//! which is the only crate allowed to talk to PostgreSQL.
use crate::requests::money;
use serde_json::{json, Map, Value};

/// `days = min(max(days, 1), 365)`.
///
/// Python's `int` is unbounded and `days: int` accepts values beyond 64 bits (`10**24` clamps to 365), so the
/// bound is applied in `i128` before any narrowing: truncating first would turn a huge value into a small or
/// negative one and clamp to 1 instead of 365.
pub fn clamp_days(days: i128) -> i64 {
    days.clamp(1, 365) as i64
}

/// Python's `html.escape` with `quote=True`: exactly these five characters, nothing else.
/// Non-ASCII text passes through unchanged, so the report stays byte-identical for accented tenant names.
pub fn html_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            other => out.push(other),
        }
    }
    out
}

/// `f"{value:.1f}"`: one decimal, round-half-even on the exact binary value, as Python's `format` does.
/// Rust's `{:.1}` is also round-half-even on the binary value, so they agree; the wrapper exists to keep
/// the call sites honest about which formatting rule they are reproducing.
pub fn f1(value: f64) -> String {
    format!("{:.1}", value)
}

/// `f"{r['created_at']:%b %d}"` for an ISO-8601 timestamp: `Nov 09` (the day is zero-padded).
pub fn month_day(iso_text: &str) -> String {
    const MONTHS: [&str; 12] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    let bytes = iso_text.as_bytes();
    if bytes.len() < 10 {
        return String::new();
    }
    let Ok(year) = iso_text[0..4].parse::<i32>() else {
        return String::new();
    };
    let Ok(month) = iso_text[5..7].parse::<usize>() else {
        return String::new();
    };
    let Ok(day) = iso_text[8..10].parse::<u32>() else {
        return String::new();
    };
    let _ = year;
    if !(1..=12).contains(&month) {
        return String::new();
    }
    format!("{} {:02}", MONTHS[month - 1], day)
}

/// Python's `str.title()`: a letter starts an uppercase run unless the previous character is a letter.
pub fn title(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut prev_is_alpha = false;
    for c in s.chars() {
        if c.is_alphabetic() {
            if prev_is_alpha {
                out.extend(c.to_lowercase());
            } else {
                out.extend(c.to_uppercase());
            }
            prev_is_alpha = true;
        } else {
            out.push(c);
            prev_is_alpha = false;
        }
    }
    out
}

/// `_money` in `main.py`, kept as a local alias so the call sites read like the Python.
pub fn report_money(cents: i64) -> String {
    money(cents)
}

/// One `<div class="c">` card.
fn card(label: &str, value: &str) -> String {
    format!("<div class=\"c\"><b>{value}</b><span>{label}</span></div>")
}

/// The two `<rect>` bars for one day.
fn bars_for_day(
    index: usize,
    conversations: i64,
    leads: i64,
    peak: i64,
    bar_w: f64,
    accent: &str,
) -> String {
    let x = index as f64 * bar_w;
    let h_c = 100.0 * conversations as f64 / peak as f64;
    let h_l = 100.0 * leads as f64 / peak as f64;
    let width = f1(f64::max(bar_w * 0.4, 1.0));
    format!(
        "<rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"#94a3b8\"/><rect x=\"{}\" y=\"{}\" width=\"{}\" height=\"{}\" fill=\"{}\"/>",
        f1(x),
        f1(110.0 - h_c),
        width,
        f1(h_c),
        f1(x + bar_w * 0.45),
        f1(110.0 - h_l),
        width,
        f1(h_l),
        html_escape(accent),
    )
}

/// One `<tr>` of the recent-leads table.
fn lead_row(row: &Value) -> String {
    let created = row.get("created_at").and_then(Value::as_str).unwrap_or("");
    let name = row.get("name").and_then(Value::as_str).unwrap_or("");
    let message = row.get("message").and_then(Value::as_str).unwrap_or("");
    let channel = row.get("channel").and_then(Value::as_str).unwrap_or("");
    let status = row.get("status").and_then(Value::as_str).unwrap_or("");
    let score_label = row.get("score_label").and_then(Value::as_str).unwrap_or("");
    // `(r['name'] or 'Visitor').split(' ')[0]`
    let who = if name.is_empty() { "Visitor" } else { name };
    let first = who.split(' ').next().unwrap_or("");
    // `r['message'][:140]` slices characters, not bytes.
    let short: String = message.chars().take(140).collect();
    // `(r['score_label'] or 'cold').title()`
    let label = if score_label.is_empty() {
        "cold"
    } else {
        score_label
    };
    format!(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
        html_escape(&month_day(created)),
        html_escape(first),
        html_escape(&short),
        html_escape(channel),
        html_escape(status),
        html_escape(&title(label)),
    )
}

/// A stats mapping exactly as `_stats` returns it; the caller supplies the aggregates from SQL.
pub struct Stats<'a> {
    pub days: i64,
    pub tenant: &'a Value,
    pub conversations_by_channel: &'a [(String, i64)],
    pub leads_by_status: &'a [(String, i64)],
    pub appointments: i64,
    pub quote_guard_interventions: i64,
    pub sent_by_channel: &'a [(String, i64)],
    pub daily: &'a [(String, i64, i64)],
    pub won_value_cents: i64,
}

impl Stats<'_> {
    fn total_convs(&self) -> i64 {
        self.conversations_by_channel.iter().map(|(_, n)| n).sum()
    }

    fn total_leads(&self) -> i64 {
        self.leads_by_status.iter().map(|(_, n)| n).sum()
    }

    fn lead_value_cents(&self) -> i64 {
        self.tenant
            .get("lead_value_cents")
            .and_then(Value::as_i64)
            .unwrap_or(0)
    }

    /// `round(total_leads / total_convs, 3) if total_convs else 0`
    fn lead_rate(&self) -> f64 {
        let convs = self.total_convs();
        if convs == 0 {
            return 0.0;
        }
        round_half_even_3(self.total_leads() as f64 / convs as f64)
    }

    fn estimated_pipeline_cents(&self) -> i64 {
        self.total_leads() * self.lead_value_cents()
    }

    /// The `_stats` return value, for comparison against the live Python if it is ever exposed.
    pub fn as_json(&self) -> Value {
        let mut by_channel = Map::new();
        for (channel, n) in self.conversations_by_channel {
            by_channel.insert(channel.clone(), json!(n));
        }
        let mut status_counts = Map::new();
        for (status, n) in self.leads_by_status {
            status_counts.insert(status.clone(), json!(n));
        }
        let mut sent = Map::new();
        for (channel, n) in self.sent_by_channel {
            sent.insert(channel.clone(), json!(n));
        }
        let daily: Vec<Value> = self
            .daily
            .iter()
            .map(|(day, conversations, leads)| json!({"day": day, "conversations": conversations, "leads": leads}))
            .collect();
        json!({
            "days": self.days,
            "conversations": self.total_convs(),
            "by_channel": Value::Object(by_channel),
            "leads": self.total_leads(),
            "leads_by_status": Value::Object(status_counts),
            "lead_rate": self.lead_rate(),
            "appointments": self.appointments,
            "estimated_pipeline_cents": self.estimated_pipeline_cents(),
            "won_value_cents": self.won_value_cents,
            "quote_guard_interventions": self.quote_guard_interventions,
            "messages_sent": Value::Object(sent),
            "daily": daily,
        })
    }
}

/// Python's `round(x, 3)` on a positive ratio: round-half-even at three decimals.
fn round_half_even_3(x: f64) -> f64 {
    let scaled = x * 1000.0;
    let r = if scaled.fract() == 0.5 {
        // banker's rounding: to the even neighbour
        let f = scaled.floor();
        if (f as i64) % 2 == 0 {
            f
        } else {
            f + 1.0
        }
    } else {
        format!("{scaled:.0}").parse::<f64>().unwrap_or(0.0)
    };
    r / 1000.0
}

/// `client_report`: the whole HTML page. `lead_rows` are the rows of the recent-leads query, already
/// newest-first, exactly as `LIMIT 25` returns them.
pub fn client_report(stats: &Stats, lead_rows: &[Value]) -> String {
    let tenant = stats.tenant;
    let daily = stats.daily;
    let peak = daily
        .iter()
        .map(|(_, c, l)| (*c).max(*l))
        .max()
        .unwrap_or(0)
        .max(1);
    let bar_w = 600.0 / (daily.len().max(1) as f64);
    let accent = tenant
        .get("accent_color")
        .and_then(Value::as_str)
        .unwrap_or("");
    let bars: String = daily
        .iter()
        .enumerate()
        .map(|(i, (_, c, l))| bars_for_day(i, *c, *l, peak, bar_w, accent))
        .collect();

    let rows: String = lead_rows.iter().map(lead_row).collect();
    let rows = if rows.is_empty() {
        "<tr><td colspan=6>No leads yet.</td></tr>".to_string()
    } else {
        rows
    };

    let pipeline = stats.estimated_pipeline_cents();
    let cards: String = [
        card("Visitor conversations", &stats.total_convs().to_string()),
        card("Leads captured", &stats.total_leads().to_string()),
        card("Appointments booked", &stats.appointments.to_string()),
        card(
            "Estimated pipeline",
            &if pipeline != 0 {
                report_money(pipeline)
            } else {
                "-".to_string()
            },
        ),
    ]
    .concat();

    let name = html_escape(tenant.get("name").and_then(Value::as_str).unwrap_or(""));
    let accent_escaped = html_escape(accent);
    let days = stats.days;
    format!(
        r#"<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>{name} - AI guide report</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;background:#f6f7f9;color:#111}}
 header{{background:{accent_escaped};color:#fff;padding:20px 24px}}
 main{{max-width:760px;margin:24px auto;padding:0 16px}}
 .g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
 .c{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8}}
 .c b{{display:block;font-size:26px}} .c span{{color:#666;font-size:13px}}
 section{{background:#fff;border-radius:10px;padding:14px;border:1px solid #e3e5e8;margin-top:16px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}} td,th{{text-align:left;padding:6px;border-bottom:1px solid #eee}}
 small{{color:#666}}
</style></head><body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">AI guide results - last {days} days</small></header>
<main>
<div class="g">{cards}</div>
<section><b>Daily activity</b> <small>grey = conversations, colour = leads</small>
<svg viewBox="0 0 600 115" width="100%" role="img" aria-label="Daily conversations and leads">{bars}</svg></section>
<section><b>Recent leads</b><table><tr><th>Date</th><th>Who</th><th>What they wanted</th><th>Via</th><th>Status</th><th>Interest</th></tr>{rows}</table></section>
<p><small>Estimated pipeline = leads x the average lead value agreed with your provider. Contact details are not shown on this page.</small></p>
</main></body></html>"#
    )
}
