use concierge_core::identity::extract_details;
use serde_json::Value;
#[test]
fn current_python_identity_extraction() {
    let cases: Value =
        serde_json::from_str(include_str!("../parity/identity_vectors.json")).unwrap();
    for c in cases.as_array().unwrap() {
        assert_eq!(
            extract_details(
                c["text"].as_str().unwrap(),
                c["cc"].as_str().unwrap(),
                c["allow_phone"].as_bool().unwrap()
            ),
            c["out"],
            "{c}"
        );
    }
}
