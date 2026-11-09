//! Batch 8: the SSRF guard, against live `ipaddress` and `urlsplit`.
use concierge_core::public_fetch::{addresses_are_public, is_global, url_verdict, UrlVerdict};
use serde::Deserialize;

#[derive(Deserialize)]
struct V {
    ip: Vec<Ip>,
    urls: Vec<U>,
    python: String,
}
#[derive(Deserialize)]
struct Ip {
    ip: String,
    out: Option<bool>,
}
#[derive(Deserialize)]
struct U {
    url: String,
    host: String,
    out: String,
}

fn load() -> V {
    serde_json::from_str(
        &std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/parity/vectors8.json"))
            .unwrap(),
    )
    .unwrap()
}

#[test]
fn global_address_rules_match_python() {
    let v = load();
    let tables: serde_json::Value =
        serde_json::from_str(include_str!("../src/ip_tables.json")).unwrap();
    assert_eq!(
        tables["python"].as_str().unwrap(),
        v.python,
        "regenerate src/ip_tables.json with the same interpreter as the vectors"
    );
    let (mut compared, mut declined) = (0, 0);
    for c in &v.ip {
        match (is_global(&c.ip), c.out) {
            (Some(got), Some(want)) => {
                assert_eq!(got, want, "ip {:?}", c.ip);
                compared += 1;
            }
            // Python raises, or accepts a form Rust's parser does not (scope ids). Rust must never call such an address public.
            (None, _) => {
                assert!(
                    addresses_are_public(&[&c.ip]).is_err(),
                    "{:?} must not pass as public",
                    c.ip
                );
                declined += 1;
            }
            (Some(got), None) => panic!(
                "Rust accepted {:?} (global={got}) but Python rejects it",
                c.ip
            ),
        }
    }
    assert!(compared > 800, "only {compared} compared");
    println!("ip cases compared {compared}, declined {declined}");
}

#[test]
fn fetch_url_rule_matches_python() {
    for c in load().urls {
        let want = match c.out.as_str() {
            "allowed" => UrlVerdict::Allowed,
            "not_same_site" => UrlVerdict::NotSameSitePublicHttps,
            _ => UrlVerdict::Unparseable,
        };
        assert_eq!(
            url_verdict(&c.url, &c.host),
            want,
            "url {:?} host {:?}",
            c.url,
            c.host
        );
    }
}

#[test]
fn resolved_address_set_rule() {
    assert!(addresses_are_public(&["8.8.8.8", "2606:4700:4700::1111"]).is_ok());
    assert!(addresses_are_public(&[]).is_err());
    assert!(
        addresses_are_public(&["8.8.8.8", "10.0.0.1"]).is_err(),
        "one private address poisons the set (DNS rebinding mix)"
    );
    assert!(
        addresses_are_public(&["169.254.169.254"]).is_err(),
        "cloud metadata endpoint"
    );
    assert!(
        addresses_are_public(&["::ffff:127.0.0.1"]).is_err(),
        "IPv4-mapped loopback"
    );
}
