//! Schemas from the actual Python API, including strict money/stock integers.
use concierge_core::{pydantic, requests};
use serde_json::Value;
#[test]
fn current_owner_and_action_models() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("../parity/owner_model_vectors.json")).unwrap();
    for (index, case) in cases.iter().enumerate() {
        let got = requests::validate(case["model"].as_str().unwrap(), &case["body"]);
        if let Some(expected) = case.get("result") {
            assert_eq!(got, Ok(expected.clone()), "case {index}: {case}")
        } else {
            match got {
                Err(requests::Outcome::Errors(errors)) => assert_eq!(
                    pydantic::errors_json(&errors),
                    case["errors"],
                    "case {index}: {case}"
                ),
                other => panic!("case {index}: {case}, got {other:?}"),
            }
        }
    }
}
