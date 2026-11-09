use base64::Engine;
use concierge_social::guardrails::{check_post, Fact, PostInput, Rules, WarningRule};
use concierge_social::vault::{account_label, Vault};
use serde_json::json;

fn vault() -> Vault {
    let key = base64::engine::general_purpose::STANDARD.encode([42u8; 32]);
    Vault::from_base64_key(&key).expect("valid key")
}

fn post(network: &str, content: &str) -> PostInput {
    PostInput {
        content: content.into(),
        networks: vec![network.into()],
        ..Default::default()
    }
}

#[test]
fn vault_roundtrip_and_distinct_nonce() {
    let v = vault();
    let label = account_label("tenant-a", "bluesky", "alice");
    let first = v.seal("secret-token", &label).unwrap();
    let second = v.seal("secret-token", &label).unwrap();
    assert_ne!(first, second);
    assert_eq!(v.open(&first, &label).unwrap(), "secret-token");
}

#[test]
fn vault_rejects_wrong_tenant_or_account() {
    let v = vault();
    let sealed = v
        .seal("secret", &account_label("tenant-a", "x", "user-1"))
        .unwrap();
    assert!(v
        .open(&sealed, &account_label("tenant-b", "x", "user-1"))
        .is_err());
    assert!(v
        .open(&sealed, &account_label("tenant-a", "x", "user-2"))
        .is_err());
}

#[test]
fn vault_rejects_tampering_and_invalid_key() {
    let v = vault();
    let sealed = v.seal("secret", "label").unwrap();
    let mut bytes = base64::engine::general_purpose::STANDARD
        .decode(sealed)
        .unwrap();
    *bytes.last_mut().unwrap() ^= 1;
    let tampered = base64::engine::general_purpose::STANDARD.encode(bytes);
    assert!(v.open(&tampered, "label").is_err());
    assert!(Vault::from_base64_key("not-base64!!").is_err());
}

#[test]
fn rejects_over_limit() {
    let p = post("bluesky", &"a".repeat(301));
    let check = check_post(&p, &Rules::default());
    assert!(!check.ok);
    assert!(check.errors.iter().any(|e| e.code == "over_limit"));
}

#[test]
fn x_links_count_as_fixed_length() {
    let mut p = post("x", &"a".repeat(256));
    p.link = "https://example.com/short".into();
    let check = check_post(&p, &Rules::default());
    assert!(check.ok, "{:?}", check.errors);
    assert_eq!(check.networks["x"].length, 280);
    p.content.push('a');
    assert!(!check_post(&p, &Rules::default()).ok);
}

#[test]
fn instagram_requires_media() {
    let p = post("instagram", "A product announcement");
    let check = check_post(&p, &Rules::default());
    assert!(check.errors.iter().any(|e| e.code == "media_required"));
    let mut with_media = p;
    with_media.media_count = 1;
    assert!(check_post(&with_media, &Rules::default()).ok);
}

#[test]
fn rejects_excess_instagram_hashtags() {
    let mut p = post("instagram", "Hello");
    p.media_count = 1;
    p.hashtags = (0..31)
        .map(|i| format!("#tag{i}"))
        .collect::<Vec<_>>()
        .join(" ");
    assert!(check_post(&p, &Rules::default())
        .errors
        .iter()
        .any(|e| e.code == "too_many_hashtags"));
}

#[test]
fn rejects_claim_contradicting_verified_fact() {
    let mut rules = Rules::default();
    rules.facts.push(Fact {
        key: "experience_years".into(),
        value: json!("10"),
        claim_regex: r"(\d+) years of experience".into(),
    });
    let p = post("bluesky", "We have 25 years of experience");
    assert!(check_post(&p, &rules)
        .errors
        .iter()
        .any(|e| e.code == "unverified_claim"));
}

#[test]
fn rejects_forbidden_phrases() {
    let mut rules = Rules::default();
    rules.forbidden_phrases.push("guaranteed results".into());
    let p = post("bluesky", "Guaranteed Results today");
    assert!(check_post(&p, &rules)
        .errors
        .iter()
        .any(|e| e.code == "forbidden_phrase"));
}

#[test]
fn warnings_do_not_block() {
    let mut rules = Rules::default();
    rules.warnings.push(WarningRule {
        id: "caution".into(),
        pattern: "limited time".into(),
        message: "Verify urgency claim".into(),
    });
    let check = check_post(&post("bluesky", "Limited time promotion"), &rules);
    assert!(check.ok);
    assert!(check.warnings.iter().any(|w| w.code == "caution"));
}

#[test]
fn unknown_network_is_rejected() {
    let check = check_post(&post("unknown-network", "Test"), &Rules::default());
    assert!(!check.ok);
    assert!(check.errors.iter().any(|e| e.code == "unknown_network"));
}

#[test]
fn x_composer_fits_unicode_and_counts_links_before_approval() {
    use concierge_social::{
        composer::{compose, Brief},
        model::Account,
    };
    let a = Account {
        id: "x-account".into(),
        customer_id: "owner".into(),
        network: "x".into(),
        display_name: "X".into(),
        external_id: "123".into(),
        needs_reauth: false,
        expires_at: None,
    };
    let b = Brief {
        content: "字".repeat(200),
        account_ids: vec![a.id.clone()],
        link: "https://example.com/a/long/destination/path".into(),
        hashtags: "#office".into(),
        media: vec![],
        video: None,
    };
    let v = compose(&b, &[a], &Rules::default()).unwrap();
    assert!(v[0].errors.is_empty(), "{:?}", v[0].errors);
    assert!(v[0].length <= 280);
    assert!(v[0].content.ends_with('…'));
    assert!(!v[0].warnings.is_empty());
    assert_eq!(v[0].link, b.link);
}
