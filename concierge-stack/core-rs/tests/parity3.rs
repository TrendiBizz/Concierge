//! Batch 3: quotation maths, fmt_local, local-time resolution and booking wording, against the live Python.
use chrono::{DateTime, NaiveDateTime, Utc};
use chrono_tz::Tz;
use concierge_core::{booking_text, quotation, schedule};
use serde::Deserialize;
use serde_json::{json, Value};

#[derive(Deserialize)]
struct V {
    quote: Vec<Q>,
    fmt: Vec<Fmt>,
    resolve: Vec<Res>,
    wording: Vec<Word>,
}
#[derive(Deserialize)]
struct Q {
    lines: Vec<L>,
    tax: i64,
    out: Value,
}
#[derive(Deserialize)]
struct L {
    description: String,
    quantity: String,
    unit_price_cents: i64,
}
#[derive(Deserialize)]
struct Fmt {
    tz: String,
    when: i64,
    out: String,
}
#[derive(Deserialize)]
struct Res {
    tz: String,
    local: String,
    out: Option<i64>,
}
#[derive(Deserialize)]
struct Word {
    tz: String,
    when: i64,
    cal: Option<String>,
    inv: Option<String>,
    dup: bool,
    name: String,
    phone: String,
    email: String,
    result: Value,
    read_back: String,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors3.json"))
            .unwrap(),
    )
    .unwrap()
}
fn ts(n: i64) -> DateTime<Utc> {
    DateTime::from_timestamp(n, 0).unwrap()
}

#[test]
fn quotation_maths_match_python() {
    let (mut compared, mut unsupported) = (0, 0);
    for (i, c) in load().quote.iter().enumerate() {
        let lines: Vec<quotation::Line> = c
            .lines
            .iter()
            .map(|l| quotation::Line {
                description: l.description.clone(),
                quantity: l.quantity.clone(),
                unit_price_cents: l.unit_price_cents,
            })
            .collect();
        // Forms Python accepts but this port declines (exponent / underscore) are counted, never silently passed.
        if lines
            .iter()
            .any(|l| quotation::parse_quantity(&l.quantity) == quotation::Quantity::Unsupported)
        {
            unsupported += 1;
            continue;
        }
        compared += 1;
        match (quotation::calculate(&lines, c.tax), c.out.get("ok")) {
            (Ok(got), Some(want)) => {
                let got = json!({"lines": got.lines, "subtotal": got.subtotal as i64, "tax": got.tax as i64, "total": got.total as i64});
                assert_eq!(
                    &got,
                    want,
                    "quote case {i}: {:?} tax {}",
                    c.lines
                        .iter()
                        .map(|l| (&l.quantity, l.unit_price_cents))
                        .collect::<Vec<_>>(),
                    c.tax
                );
            }
            (Err(_), None) => {}
            (Err(e), Some(_)) => panic!(
                "quote case {i}: Python accepts but Rust rejected: {e} {:?}",
                c.lines
                    .iter()
                    .map(|l| (&l.description, &l.quantity, l.unit_price_cents))
                    .collect::<Vec<_>>()
            ),
            (Ok(_), None) => panic!(
                "quote case {i}: Python rejects but Rust accepted: {:?} tax {}",
                c.lines
                    .iter()
                    .map(|l| (&l.description, &l.quantity, l.unit_price_cents))
                    .collect::<Vec<_>>(),
                c.tax
            ),
        }
    }
    assert!(
        compared > 600,
        "only {compared} compared ({unsupported} unsupported)"
    );
    println!("quote cases compared: {compared}, unsupported forms skipped: {unsupported}");
}

#[test]
fn quotation_status_transitions() {
    assert_eq!(quotation::allowed_from("reviewed"), Some(&["draft"][..]));
    assert_eq!(quotation::allowed_from("accepted"), Some(&["reviewed"][..]));
    assert_eq!(quotation::allowed_from("void").unwrap().len(), 4);
    assert_eq!(quotation::allowed_from("draft"), None);
}

#[test]
fn fmt_local_matches_python() {
    for (i, c) in load().fmt.iter().enumerate() {
        assert_eq!(
            schedule::fmt_local(c.tz.parse::<Tz>().unwrap(), ts(c.when)),
            c.out,
            "fmt case {i}: {} {}",
            c.tz,
            c.when
        );
    }
}

#[test]
fn local_time_resolution_matches_python_dst() {
    for c in load().resolve {
        let tz: Tz = c.tz.parse().unwrap();
        let naive = NaiveDateTime::parse_from_str(&c.local, "%Y-%m-%dT%H:%M:%S")
            .or_else(|_| NaiveDateTime::parse_from_str(&c.local, "%Y-%m-%dT%H:%M"))
            .unwrap();
        let got = schedule::resolve_local(tz, naive)
            .ok()
            .map(|d| d.timestamp());
        assert_eq!(got, c.out, "{} {}", c.tz, c.local);
    }
}

#[test]
fn booking_wording_matches_python() {
    for (i, c) in load().wording.iter().enumerate() {
        let tz: Tz = c.tz.parse().unwrap();
        let appt = booking_text::Appointment {
            id: "abc-123",
            starts_at: ts(c.when),
            calendar_state: c.cal.as_deref(),
            invitation_state: c.inv.as_deref(),
        };
        assert_eq!(
            booking_text::booking_result(tz, &appt, c.dup),
            c.result,
            "wording case {i}"
        );
        assert_eq!(
            booking_text::read_back(&c.name, tz, ts(c.when), &c.phone, &c.email),
            c.read_back,
            "read_back case {i}"
        );
    }
}
