//! Batch 23: the owner-portal origin boundary and the admin-token gate against the live functions.
use concierge_core::edge::{self, Boundary};
use serde_json::{json, Value};

#[test]
fn edge_rules_match_python() {
    let v: Value = serde_json::from_str(include_str!("../parity/vectors23.json")).unwrap();
    let (mut refused, mut protected) = (0, 0);
    for c in v["boundary"].as_array().unwrap() {
        let got = edge::owner_boundary(
            c["path"].as_str().unwrap(),
            c["scheme"].as_str().unwrap(),
            c["netloc"].as_str().unwrap(),
            c["origin"].as_str(),
            c["base"].as_str().unwrap(),
        );
        let (passed, status, headers) = match got {
            Boundary::Passthrough => (true, 200, json!({})),
            Boundary::Protected => (
                true,
                200,
                json!(edge::PROTECTED_HEADERS
                    .iter()
                    .map(|(k, v)| (k.to_string(), json!(v)))
                    .collect::<serde_json::Map<_, _>>()),
            ),
            Boundary::Refuse => (false, 403, json!({"cache-control": "no-store"})),
        };
        assert_eq!(passed, c["passed"].as_bool().unwrap(), "{c}");
        assert_eq!(status, c["status"].as_u64().unwrap(), "{c}");
        // a refusal also carries Starlette's own content-length; only the header we control is compared
        let want: serde_json::Map<String, Value> = c["headers"]
            .as_object()
            .unwrap()
            .iter()
            .filter(|(k, _)| *k != "content-length")
            .map(|(k, x)| (k.clone(), x.clone()))
            .collect();
        assert_eq!(headers, Value::Object(want), "{c}");
        refused += (got == Boundary::Refuse) as i32;
        protected += (got == Boundary::Protected) as i32;
    }
    assert!(refused > 50 && protected > 50, "{refused} {protected}");
    for c in v["admin"].as_array().unwrap() {
        let got = match edge::require_admin(
            c["expected"].as_str().unwrap(),
            c["given"].as_str().unwrap(),
        ) {
            Ok(()) => json!({"ok": true}),
            Err((s, d)) => json!({"status": s, "detail": d}),
        };
        assert_eq!(got, c["out"], "{c}");
    }
}
