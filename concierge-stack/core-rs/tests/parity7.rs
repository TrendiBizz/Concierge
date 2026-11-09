//! Batch 7: sales forecast and digest, task due dates, conversation cleaners and owner credentials, against the live Python.
use chrono::DateTime;
use chrono_tz::Tz;
use concierge_core::{convo, owner_auth, sales, tasks};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
struct V {
    forecast: Vec<Fc>,
    money: Vec<Money>,
    effective: Vec<Eff>,
    digest: Vec<Dg>,
    due: Vec<Due>,
    task_due: Vec<TaskDue>,
    titles: Vec<Title>,
    utm: Vec<Utm>,
    sessions: Vec<Sess>,
    auth_digest: Vec<AD>,
    hashes: Vec<Hash>,
    verify: Vec<Ver>,
    emails: Vec<Em>,
}
#[derive(Deserialize)]
struct Fc {
    rows: Vec<Value>,
    avg: Option<i64>,
    per: usize,
    out: Value,
}
#[derive(Deserialize)]
struct Money {
    cents: i64,
    out: String,
}
#[derive(Deserialize)]
struct Eff {
    lead: Value,
    avg: Option<i64>,
    out: i64,
}
#[derive(Deserialize)]
struct Dg {
    name: String,
    s: Sm,
    subject: String,
    body: String,
}
#[derive(Deserialize)]
struct Sm {
    days: i64,
    new_leads: i64,
    contacted: i64,
    booked: i64,
    won: i64,
    lost: i64,
    won_value_cents: i64,
    open_value_cents: i64,
    weighted_value_cents: i64,
    overdue_todos: i64,
    leads_waiting: Option<i64>,
}
#[derive(Deserialize)]
struct Due {
    wd: u32,
    hour: u32,
    out: bool,
}
#[derive(Deserialize)]
struct TaskDue {
    tz: Option<String>,
    sla: Option<i64>,
    hot: bool,
    now: i64,
    out: i64,
}
#[derive(Deserialize)]
struct Title {
    #[serde(rename = "in")]
    input: Option<String>,
    out: Value,
}
#[derive(Deserialize)]
struct Utm {
    utm: serde_json::Map<String, Value>,
    out: serde_json::Map<String, Value>,
}
#[derive(Deserialize)]
struct Sess {
    #[serde(rename = "in")]
    input: String,
    out: Value,
}
#[derive(Deserialize)]
struct AD {
    #[serde(rename = "in")]
    input: String,
    out: String,
}
#[derive(Deserialize)]
struct Hash {
    pw: String,
    salt_hex: String,
    out: Value,
}
#[derive(Deserialize)]
struct Ver {
    pw: String,
    stored: String,
    out: bool,
}
#[derive(Deserialize)]
struct Em {
    #[serde(rename = "in")]
    input: String,
    out: Value,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors7.json"))
            .unwrap(),
    )
    .unwrap()
}
fn res(r: Result<String, &str>) -> Value {
    match r {
        Ok(v) => serde_json::json!({"ok": v}),
        Err(e) => serde_json::json!({"err": e}),
    }
}

#[test]
fn sales_forecast_money_and_digest_match_python() {
    let v = load();
    for (i, c) in v.forecast.iter().enumerate() {
        assert_eq!(
            sales::forecast(&c.rows, c.avg, c.per),
            c.out,
            "forecast case {i}"
        );
    }
    for c in &v.money {
        assert_eq!(sales::money(c.cents), c.out, "money {}", c.cents);
    }
    for c in &v.effective {
        assert_eq!(sales::effective_value(&c.lead, c.avg), c.out);
    }
    for (i, c) in v.digest.iter().enumerate() {
        let s = &c.s;
        let sm = sales::Summary {
            days: s.days,
            new_leads: s.new_leads,
            contacted: s.contacted,
            booked: s.booked,
            won: s.won,
            lost: s.lost,
            won_value_cents: s.won_value_cents,
            open_value_cents: s.open_value_cents,
            weighted_value_cents: s.weighted_value_cents,
            overdue_todos: s.overdue_todos,
            leads_waiting: s.leads_waiting,
        };
        assert_eq!(
            sales::digest_text(&c.name, &sm),
            (c.subject.clone(), c.body.clone()),
            "digest {i}"
        );
    }
    for c in &v.due {
        assert_eq!(
            sales::digest_is_due(c.wd, c.hour),
            c.out,
            "due wd {} h {}",
            c.wd,
            c.hour
        );
    }
}

#[test]
fn task_due_dates_and_titles_match_python() {
    let v = load();
    for (i, c) in v.task_due.iter().enumerate() {
        let tz: Tz =
            c.tz.as_deref()
                .filter(|t| !t.is_empty())
                .unwrap_or("UTC")
                .parse()
                .unwrap();
        let got = tasks::default_follow_up_due(
            tz,
            c.sla,
            c.hot,
            DateTime::from_timestamp(c.now, 0).unwrap(),
        );
        assert_eq!(
            got.timestamp(),
            c.out,
            "task due case {i}: {:?} now {} hot {}",
            c.tz,
            c.now,
            c.hot
        );
    }
    for c in &v.titles {
        assert_eq!(
            res(tasks::clean_title(c.input.as_deref().unwrap_or(""))),
            c.out,
            "title {:?}",
            c.input
        );
    }
}

#[test]
fn conversation_cleaners_match_python() {
    let v = load();
    for (i, c) in v.utm.iter().enumerate() {
        let got = convo::clean_utm(&c.utm).expect("supported value types");
        let want: Vec<(String, String)> = c
            .out
            .iter()
            .map(|(k, v)| (k.clone(), v.as_str().unwrap().to_string()))
            .collect();
        assert_eq!(got, want, "utm case {i}");
    }
    for c in &v.sessions {
        let got = match convo::clean_session(&c.input) {
            Ok(s) => serde_json::json!({"ok": s}),
            Err(e) => serde_json::json!({"err": [400, e]}),
        };
        assert_eq!(got, c.out, "session {:?}", c.input);
    }
}

#[test]
fn owner_credentials_match_python() {
    let v = load();
    for c in &v.auth_digest {
        assert_eq!(owner_auth::digest(&c.input), c.out);
    }
    for c in &v.hashes {
        let salt: [u8; 16] = (0..16)
            .map(|i| u8::from_str_radix(&c.salt_hex[i * 2..i * 2 + 2], 16).unwrap())
            .collect::<Vec<_>>()
            .try_into()
            .unwrap();
        assert_eq!(
            res(owner_auth::password_hash_with_salt(
                &c.pw,
                &salt,
                owner_auth::ITERATIONS
            )),
            c.out,
            "hash of {:?}",
            c.pw.chars().count()
        );
    }
    for c in &v.verify {
        assert_eq!(
            owner_auth::verify_password(&c.pw, &c.stored),
            c.out,
            "verify {:?} vs {:?}",
            c.pw,
            c.stored
        );
    }
    for c in &v.emails {
        assert_eq!(
            res(owner_auth::clean_email(&c.input)),
            c.out,
            "email {:?}",
            c.input
        );
    }
}
