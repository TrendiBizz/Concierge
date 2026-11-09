use base64::Engine;
use concierge_social::{linkedin, store::Store, vault::Vault};
#[test]
fn pages_use_separate_app_permissions_and_single_use_tenant_state() {
    let store = Store::open_memory().unwrap();
    for id in ["a", "b"] {
        store.create_customer(id, id, "owner@example.com").unwrap();
    }
    let vault =
        Vault::from_base64_key(&base64::engine::general_purpose::STANDARD.encode([17u8; 32]))
            .unwrap();
    let cfg = linkedin::Config {
        client_id: "dedicated-pages-app".into(),
        client_secret: "private-test-secret".into(),
        callback: "https://example.com/owner/social/oauth/callback".into(),
    };
    let start = linkedin::start_organizations(&store, &vault, "a", &cfg).unwrap();
    let url = reqwest::Url::parse(&start.authorization_url).unwrap();
    let pairs: std::collections::HashMap<_, _> = url.query_pairs().collect();
    assert_eq!(pairs["client_id"], "dedicated-pages-app");
    assert_eq!(pairs["scope"], "r_organization_admin w_organization_social");
    assert!(store
        .oauth_consume("b", "linkedin_organization", &start.state)
        .is_err());
    assert!(store.oauth_consume("a", "linkedin", &start.state).is_err());
    assert!(store
        .oauth_consume("a", "linkedin_organization", &start.state)
        .is_ok());
    assert!(store
        .oauth_consume("a", "linkedin_organization", &start.state)
        .is_err());
}
