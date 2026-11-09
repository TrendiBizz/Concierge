//! Batch 30: the response shapes of the read-only admin listing routes (scoring, sla, campaigns, pipeline, sales summary,
//! stats). The vectors are the output of the LIVE Python handlers with only the database stubbed
//! (`parity/gen_vectors30.py` -> `parity/vectors30.json`); the bodies are compared as compact JSON text so key order counts.
//! The SQL itself is proven by `QA/verification/rust_server_parity.py`.
use concierge_core::admin_views as v;
use serde_json::Value;

fn load() -> Value {
    serde_json::from_str(include_str!("../parity/vectors30.json")).unwrap()
}

fn cases_of(kind: &str) -> Vec<Value> {
    load()["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|c| c["kind"] == kind)
        .cloned()
        .collect()
}

fn text(v: &Value) -> String {
    serde_json::to_string(v).unwrap()
}

fn pairs(v: &Value) -> Vec<(String, i64)> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|p| (p[0].as_str().unwrap().to_string(), p[1].as_i64().unwrap()))
        .collect()
}

fn expect(case: &Value, got: Option<String>, label: &str) {
    match (case.get("error"), got) {
        (Some(_), None) => {}
        (Some(_), Some(g)) => panic!("{label}: Python raised (500) but Rust rendered {g}"),
        (None, Some(g)) => assert_eq!(g, case["out"].as_str().unwrap(), "{label}: {case}"),
        (None, None) => panic!("{label}: Rust failed where Python answered: {case}"),
    }
}

#[test]
fn scoring_describe_matches_python() {
    let cases = cases_of("scoring");
    assert!(cases.len() >= 25);
    for c in &cases {
        let got = text(&serde_json::json!({"weights": v::describe_scoring(Some(&c["scoring"]))}));
        expect(c, Some(got), "scoring");
    }
}

#[test]
fn sla_body_matches_python() {
    let cases = cases_of("sla");
    assert!(cases.len() >= 40);
    for c in &cases {
        let minutes = c["tenant"]["sla_minutes"].as_i64().unwrap_or(0);
        // `sla.overdue` returns nothing at all when the feature is off, whatever rows the stub holds.
        let rows: Vec<Value> = if minutes > 0 {
            c["rows"].as_array().unwrap().clone()
        } else {
            vec![]
        };
        expect(c, Some(text(&v::sla_response(&c["tenant"], &rows))), "sla");
    }
}

#[test]
fn campaign_views_match_python() {
    let single = cases_of("campaign");
    let list = cases_of("campaign_list");
    assert!(single.len() >= 30 && list.len() >= 30);
    let mut errors = 0;
    for c in &single {
        let got = v::campaign_with_delivery(&c["campaign"], &pairs(&c["delivery"]))
            .ok()
            .map(|b| text(&b));
        errors += usize::from(got.is_none());
        expect(c, got, "campaign");
    }
    for c in &list {
        let delivery = pairs(&c["delivery"]);
        let got: Result<Vec<Value>, _> = c["campaigns"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| v::campaign_with_delivery(r, &delivery))
            .collect();
        errors += usize::from(got.is_err());
        expect(c, got.ok().map(|b| text(&Value::Array(b))), "campaign list");
    }
    assert!(errors >= 10, "the undecodable-filters cases must fail closed");
}

#[test]
fn pipeline_matches_python() {
    let cases = cases_of("pipeline");
    assert!(cases.len() >= 20);
    for c in &cases {
        let rows = c["rows"].as_array().unwrap();
        let got = v::pipeline_view(rows, c["average"].as_i64().unwrap(), 50);
        expect(c, Some(text(&got)), "pipeline");
    }
}

#[test]
fn sales_summary_matches_python() {
    let file = load();
    let board_rows = file["summary_pipeline_rows"].as_array().unwrap().clone();
    let cases = cases_of("summary");
    assert!(cases.len() >= 400);
    for c in &cases {
        let average = c["average"].as_i64().unwrap();
        let board = v::pipeline_view(&board_rows, average, 0);
        let moved = pairs(&c["moved"]);
        let won: Vec<i64> = c["won"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_i64().unwrap())
            .collect();
        let got = v::summary_view(&v::SummaryInput {
            days: c["days"].as_i64().unwrap(),
            new_leads: c["new_leads"].as_i64().unwrap(),
            moved: &moved,
            won_values: &won,
            average_cents: average,
            open_value_cents: board["open_value_cents"].as_i64().unwrap(),
            weighted_value_cents: board["weighted_value_cents"].as_i64().unwrap(),
            overdue_todos: c["overdue_todos"].as_i64().unwrap(),
            leads_waiting: c["waiting"].as_i64(),
        });
        expect(c, Some(text(&got)), "summary");
    }
}

#[test]
fn stats_match_python() {
    let cases = cases_of("stats");
    assert!(cases.len() >= 100);
    for c in &cases {
        let daily: Vec<(String, i64, i64)> = c["daily"]
            .as_array()
            .unwrap()
            .iter()
            .map(|d| {
                (
                    d[0].as_str().unwrap().to_string(),
                    d[1].as_i64().unwrap(),
                    d[2].as_i64().unwrap(),
                )
            })
            .collect();
        let got = v::stats_view(&v::StatsInput {
            days: c["days"].as_i64().unwrap(),
            conversations_by_channel: &pairs(&c["convs"]),
            leads_by_status: &pairs(&c["statuses"]),
            appointments: c["appointments"].as_i64().unwrap(),
            quote_guard_interventions: c["guard"].as_i64().unwrap(),
            sent_by_channel: &pairs(&c["sent"]),
            daily: &daily,
            lead_value_cents: c["average"].as_i64().unwrap(),
            won_value_cents: c["won_value"].as_i64().unwrap(),
        });
        expect(c, Some(text(&got)), "stats");
    }
}
