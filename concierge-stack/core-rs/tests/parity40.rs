//! Batch 40: `GET /api/v1/unsubscribe/{token}`. Expected pages and 500s are the output of the live
//! `app.main.unsubscribe_page` (`parity/gen_vectors40.py` -> `parity/vectors40.json`).
use concierge_core::unsub;
use serde_json::Value;

#[test]
fn unsubscribe_page_matches_python() {
    let v: Value = serde_json::from_str(include_str!("../parity/vectors40.json")).unwrap();
    let cases = v["cases"].as_array().unwrap();
    assert!(cases.len() > 60);
    let (mut ok, mut bad, mut err) = (0, 0, 0);
    for c in cases {
        let (secret, token) = (c["secret"].as_str().unwrap(), c["token"].as_str().unwrap());
        let got = unsub::unsubscribe_confirm_page(secret, token);
        let out = &c["out"];
        if out.get("error").is_some() {
            assert!(got.is_err(), "token {token:?} must make Python raise");
            err += 1;
            continue;
        }
        let (status, body) = got.unwrap_or_else(|_| panic!("token {token:?} must not raise"));
        assert_eq!(
            status as u64,
            out["status"].as_u64().unwrap(),
            "token {token:?}"
        );
        assert_eq!(body, out["body"].as_str().unwrap(), "token {token:?}");
        if status == 200 {
            ok += 1
        } else {
            bad += 1
        }
    }
    assert!(ok > 10 && bad > 10 && err > 0, "{ok} {bad} {err}");
}
