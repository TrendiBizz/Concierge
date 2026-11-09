//! Batch 25: the client report page. The vectors come from the live `_money` and the live `html.escape`,
//! `str.title()`, `strftime("%b %d")` and bar arithmetic that `client_report` performs
//! (`parity/gen_vectors25.py` -> `parity/vectors25.json`), so these tests compare against Python's own output
//! rather than a transcription of it. The aggregation SQL is proven by `QA/verification/rust_server_parity.py`.
use concierge_core::report;
use serde_json::Value;

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors25.json")).unwrap()
}

#[test]
fn html_escape_matches_python() {
    let v = vectors();
    let cases = v["escape"].as_array().unwrap();
    assert!(!cases.is_empty());
    for c in cases {
        let input = c["in"].as_str().unwrap();
        assert_eq!(
            report::html_escape(input),
            c["out"].as_str().unwrap(),
            "html.escape({input:?})"
        );
    }
}

#[test]
fn money_matches_python() {
    let v = vectors();
    for c in v["money"].as_array().unwrap() {
        let cents = c["cents"].as_i64().unwrap();
        assert_eq!(
            report::report_money(cents),
            c["out"].as_str().unwrap(),
            "_money({cents})"
        );
    }
}

#[test]
fn title_matches_python() {
    let v = vectors();
    for c in v["title"].as_array().unwrap() {
        let input = c["in"].as_str().unwrap();
        assert_eq!(
            report::title(input),
            c["out"].as_str().unwrap(),
            "str.title({input:?})"
        );
    }
}

#[test]
fn month_day_matches_python() {
    let v = vectors();
    for c in v["month_day"].as_array().unwrap() {
        let iso = c["iso"].as_str().unwrap();
        assert_eq!(
            report::month_day(iso),
            c["out"].as_str().unwrap(),
            "strftime(%b %d) on {iso}"
        );
    }
}

#[test]
fn clamp_days_matches_python() {
    let v = vectors();
    for c in v["clamp"].as_array().unwrap() {
        let n: i128 = c["in"].as_str().unwrap().parse().unwrap();
        assert_eq!(
            report::clamp_days(n) as i128,
            c["out"].as_i64().unwrap() as i128,
            "min(max(days,1),365) for {n}"
        );
    }
}

#[test]
fn bar_arithmetic_matches_python() {
    let v = vectors();
    let cases = v["bars"].as_array().unwrap();
    assert!(!cases.is_empty());
    for c in cases {
        let daily: Vec<(String, i64, i64)> = c["daily"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .map(|(i, d)| {
                (
                    format!("2026-11-{:02}", (i % 28) + 1),
                    d["conversations"].as_i64().unwrap(),
                    d["leads"].as_i64().unwrap(),
                )
            })
            .collect();
        let accent = c["accent"].as_str().unwrap();
        // Build the bars through the public page renderer so this covers the same code path the route uses.
        let tenant = serde_json::json!({
            "name": "T", "accent_color": accent, "lead_value_cents": 0,
        });
        let stats = report::Stats {
            days: 30,
            tenant: &tenant,
            conversations_by_channel: &[],
            leads_by_status: &[],
            appointments: 0,
            quote_guard_interventions: 0,
            sent_by_channel: &[],
            daily: &daily,
            won_value_cents: 0,
        };
        let page = report::client_report(&stats, &[]);
        let start = page
            .find(r#"aria-label="Daily conversations and leads">"#)
            .unwrap()
            + r#"aria-label="Daily conversations and leads">"#.len();
        let end = page[start..].find("</svg>").unwrap() + start;
        assert_eq!(
            &page[start..end],
            c["out"].as_str().unwrap(),
            "bars for {accent:?}"
        );
    }
}
