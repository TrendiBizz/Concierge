//! Batch 27: the sandbox demo page, `GET /demo/{slug}`. The vectors are the output of the LIVE `app.main.demo_page`
//! coroutine, with only the tenant lookup and the first-chunk query stubbed (`parity/gen_vectors27.py` ->
//! `parity/vectors27.json`), so these tests compare against Python's own HTML rather than a transcription of it.
//! The two SQL statements are proven by `QA/verification/rust_server_parity.py`.
use concierge_core::demo;
use serde_json::Value;

fn cases() -> Vec<Value> {
    let v: Value = serde_json::from_str(include_str!("../parity/vectors27.json")).unwrap();
    v["cases"].as_array().unwrap().clone()
}

fn run(case: &Value) -> Result<String, &'static str> {
    demo::demo_page(
        &case["tenant"],
        case["excerpt"].as_str(),
        i128::from(case["presenter"].as_i64().unwrap()),
    )
}

#[test]
fn page_matches_python_byte_for_byte() {
    let mut compared = 0;
    for case in cases() {
        if case.get("error").is_some() || case.get("declined").is_some() {
            continue;
        }
        let got = run(&case).unwrap_or_else(|e| panic!("{e}: {case}"));
        assert_eq!(
            got,
            case["out"].as_str().unwrap(),
            "demo_page for {}",
            case["tenant"]
        );
        compared += 1;
    }
    assert!(compared > 150, "only {compared} page vectors compared");
}

#[test]
fn inputs_python_cannot_render_fail_closed() {
    let mut checked = 0;
    for case in cases() {
        if case.get("error").is_some() {
            assert!(
                run(&case).is_err(),
                "Python raised (500) but Rust rendered: {}",
                case["tenant"]
            );
            checked += 1;
        }
    }
    assert!(checked > 50, "only {checked} error vectors checked");
}

#[test]
fn the_declined_shape_fails_closed_instead_of_guessing() {
    let declined: Vec<Value> = cases()
        .into_iter()
        .filter(|c| c.get("declined").is_some())
        .collect();
    assert!(!declined.is_empty());
    for case in declined {
        assert!(run(&case).is_err(), "{}", case["tenant"]);
    }
}

#[test]
fn excerpt_is_cut_at_700_code_points_not_bytes() {
    let tenant = serde_json::json!({
        "name": "T", "accent_color": "#000", "site_url": null, "public_key": "k", "demo_questions": []
    });
    let page = demo::demo_page(&tenant, Some(&"é".repeat(701)), 0).unwrap();
    assert!(page.contains(&format!("<p>{}</p>", "é".repeat(700))));
    assert!(!page.contains(&"é".repeat(701)));
}
