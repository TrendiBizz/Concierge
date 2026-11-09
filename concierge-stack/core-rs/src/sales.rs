//! Pipeline arithmetic and the weekly digest wording (port of the pure parts of `sales.py`).
use serde_json::{json, Map, Value};

pub const STAGES: [&str; 5] = ["new", "contacted", "booked", "won", "lost"];
pub const OPEN_STAGES: [&str; 3] = ["new", "contacted", "booked"];
const ODDS: [(&str, f64); 5] = [
    ("new", 0.10),
    ("contacted", 0.25),
    ("booked", 0.60),
    ("won", 1.0),
    ("lost", 0.0),
];

fn odds(stage: &str) -> f64 {
    ODDS.iter().find(|o| o.0 == stage).map_or(0.0, |o| o.1)
}

/// `int(x or 0)` for the numeric shapes a lead row carries.
fn int_or_zero(v: Option<&Value>) -> i64 {
    match v {
        Some(Value::Number(n)) => n
            .as_i64()
            .unwrap_or_else(|| n.as_f64().map_or(0, |f| f.trunc() as i64)),
        Some(Value::Bool(true)) => 1,
        _ => 0,
    }
}

/// A lead's own value if set, otherwise the client's average lead value.
pub fn effective_value(lead: &Value, average_cents: Option<i64>) -> i64 {
    let own = int_or_zero(lead.get("value_cents"));
    if own != 0 {
        own
    } else {
        average_cents.unwrap_or(0)
    }
}

pub fn forecast(rows: &[Value], average_cents: Option<i64>, per_stage: usize) -> Value {
    let mut counts = [0i64; 5];
    let mut values = [0i64; 5];
    let mut leads: Vec<Vec<Value>> = vec![Vec::new(); 5];
    for lead in rows {
        let status = lead
            .get("status")
            .and_then(Value::as_str)
            .filter(|s| STAGES.contains(s))
            .unwrap_or("new");
        let idx = STAGES.iter().position(|s| *s == status).unwrap();
        let value = effective_value(lead, average_cents);
        counts[idx] += 1;
        values[idx] += value;
        if leads[idx].len() < per_stage {
            let mut m = lead.as_object().cloned().unwrap_or_default();
            m.insert("effective_value_cents".into(), json!(value));
            leads[idx].push(Value::Object(m));
        }
    }
    let mut stages = Map::new();
    for (i, s) in STAGES.iter().enumerate() {
        stages.insert(
            (*s).into(),
            json!({"count": counts[i], "value_cents": values[i], "leads": leads[i]}),
        );
    }
    let open_value: i64 = OPEN_STAGES
        .iter()
        .map(|s| values[STAGES.iter().position(|x| x == s).unwrap()])
        .sum();
    let weighted_f: f64 = OPEN_STAGES.iter().fold(0.0, |acc, s| {
        acc + values[STAGES.iter().position(|x| x == s).unwrap()] as f64 * odds(s)
    });
    let mut odds_map = Map::new();
    for (k, v) in ODDS {
        odds_map.insert(k.into(), json!(v));
    }
    json!({
        "stages": stages, "open_value_cents": open_value, "weighted_value_cents": weighted_f.round_ties_even() as i64,
        "won_value_cents": values[3], "odds": odds_map,
    })
}

/// `f"${cents / 100:,.0f}"`.
pub fn money(cents: i64) -> String {
    let rounded = format!("{:.0}", cents as f64 / 100.0);
    let (neg, digits) = match rounded.strip_prefix('-') {
        Some(d) => (true, d),
        None => (false, rounded.as_str()),
    };
    let mut grouped = String::new();
    for (i, c) in digits.chars().enumerate() {
        if i > 0 && (digits.len() - i) % 3 == 0 {
            grouped.push(',');
        }
        grouped.push(c);
    }
    format!("${}{grouped}", if neg { "-" } else { "" })
}

pub struct Summary {
    pub days: i64,
    pub new_leads: i64,
    pub contacted: i64,
    pub booked: i64,
    pub won: i64,
    pub lost: i64,
    pub won_value_cents: i64,
    pub open_value_cents: i64,
    pub weighted_value_cents: i64,
    pub overdue_todos: i64,
    pub leads_waiting: Option<i64>,
}

pub fn digest_text(business: &str, s: &Summary) -> (String, String) {
    let subject = format!(
        "Your week at {business}: {} new lead(s), {} won",
        s.new_leads, s.won
    );
    let mut lines = vec![
        format!("Here is the last {} days for {business}.", s.days),
        String::new(),
        format!("New leads: {}", s.new_leads),
        format!("Moved to contacted: {}   Booked: {}", s.contacted, s.booked),
        format!(
            "Won: {} ({})   Lost: {}",
            s.won,
            money(s.won_value_cents),
            s.lost
        ),
        format!(
            "Open pipeline: {}   Weighted: {}",
            money(s.open_value_cents),
            money(s.weighted_value_cents)
        ),
        format!("To-dos overdue: {}", s.overdue_todos),
    ];
    if let Some(w) = s.leads_waiting {
        lines.push(format!("Leads waiting for a reply: {w}"));
    }
    lines.push(String::new());
    lines.push("Open the dashboard for the pipeline and to-do list.".into());
    (subject, lines.join("\n") + "\n")
}

/// Monday, between 8am and 9pm local time.
pub fn digest_is_due(weekday_from_monday: u32, hour: u32) -> bool {
    weekday_from_monday == 0 && (8..21).contains(&hour)
}
