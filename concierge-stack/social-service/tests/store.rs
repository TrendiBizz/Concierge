use concierge_social::model::{NewPost, Status};
use concierge_social::store::Store;
#[test]
fn draft_rejects_accounts_owned_by_another_customer_before_storage() {
    let store = Store::open_memory().unwrap();
    store.create_customer("a", "A", "").unwrap();
    store.create_customer("b", "B", "").unwrap();
    let (_, foreign) = draft(&store, "a");
    let own = store
        .add_account("b", "linkedin", "member", "B", "sealed", None)
        .unwrap();
    for accounts in [
        vec![foreign.clone()],
        vec![own.clone(), foreign],
        vec!["unknown".into()],
    ] {
        assert!(store
            .create_post(
                "b",
                NewPost {
                    content: "Synthetic draft".into(),
                    link: "".into(),
                    hashtags: "".into(),
                    account_ids: accounts,
                    media: vec![],
                }
            )
            .is_err());
        assert!(store.list_posts("b").unwrap().is_empty());
    }
    assert!(store
        .create_post(
            "b",
            NewPost {
                content: "Own account".into(),
                link: "".into(),
                hashtags: "".into(),
                account_ids: vec![own],
                media: vec![],
            }
        )
        .is_ok());
}
fn draft(store: &Store, tenant: &str) -> (String, String) {
    let account = store
        .add_account(tenant, "bluesky", "alice", "Alice", "encrypted", None)
        .unwrap();
    let p = store
        .create_post(
            tenant,
            NewPost {
                content: "Hello".into(),
                link: "".into(),
                hashtags: "".into(),
                account_ids: vec![account.clone()],
                media: vec![],
            },
        )
        .unwrap();
    (p.id, account)
}
#[test]
fn cross_tenant_records_are_isolated() {
    let s = Store::open_memory().unwrap();
    s.create_customer("a", "Company A", "a@example.com")
        .unwrap();
    s.create_customer("b", "Company B", "b@example.com")
        .unwrap();
    let (post, account) = draft(&s, "a");
    assert!(s.get_post("b", &post).is_err());
    assert!(s.account("b", &account).is_err());
    assert_eq!(s.list_posts("b").unwrap().len(), 0);
    assert_eq!(s.list_accounts("b").unwrap().len(), 0);
}
#[test]
fn approvals_expire_are_single_use_and_revision_bound() {
    let s = Store::open_memory().unwrap();
    s.create_customer("a", "Company A", "a@example.com")
        .unwrap();
    let (id, _) = draft(&s, "a");
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    assert!(s.create_approval("a", &id, now, now + 100).is_err());
    s.submit("a", &id).unwrap();
    let old = s.create_approval("a", &id, now, now + 100).unwrap();
    let current = s.create_approval("a", &id, now, now + 100).unwrap();
    assert!(s.decide("a", &old, true, now).is_err());
    assert!(s.decide("a", &current, true, now).is_ok());
    assert!(s.decide("a", &current, true, now).is_err());
    assert_eq!(s.get_post("a", &id).unwrap().status, Status::Scheduled);
    let claimed = s.claim_due(now).unwrap();
    assert_eq!(claimed.len(), 1);
    assert_eq!(s.claim_due(now).unwrap().len(), 0);
}
#[test]
fn approval_wrong_customer_is_rejected() {
    let s = Store::open_memory().unwrap();
    s.create_customer("a", "A", "a@example.com").unwrap();
    s.create_customer("b", "B", "b@example.com").unwrap();
    let (id, _) = draft(&s, "a");
    s.submit("a", &id).unwrap();
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    let token = s.create_approval("a", &id, now, now + 100).unwrap();
    assert!(s.decide("b", &token, true, now).is_err());
    assert_eq!(
        s.get_post("a", &id).unwrap().status,
        Status::PendingApproval
    );
}
#[test]
fn editing_invalidates_pending_tokens() {
    let s = Store::open_memory().unwrap();
    s.create_customer("a", "A", "a@example.com").unwrap();
    let (id, _) = draft(&s, "a");
    s.submit("a", &id).unwrap();
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    let token = s.create_approval("a", &id, now, now + 100).unwrap();
    s.edit_post("a", &id, "new revision".into()).unwrap();
    assert!(s.decide("a", &token, true, now).is_err());
}

#[test]
fn interrupted_publish_is_quarantined_without_replay() {
    let s = Store::open_memory().unwrap();
    s.create_customer("a", "Company A", "a@example.test")
        .unwrap();
    let (id, _) = draft(&s, "a");
    s.submit("a", &id).unwrap();
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    let token = s.create_approval("a", &id, now, now + 100).unwrap();
    s.decide("a", &token, true, now).unwrap();
    assert_eq!(s.claim_due(now).unwrap().len(), 1);
    assert_eq!(s.get_post("a", &id).unwrap().status, Status::Publishing);
    assert_eq!(s.quarantine_interrupted().unwrap(), 1);
    let p = s.get_post("a", &id).unwrap();
    assert_eq!(p.status, Status::Failed);
    assert!(p.last_error.unwrap().contains("reconcile"));
    assert_eq!(s.claim_due(now + 5).unwrap().len(), 0);
    assert_eq!(s.quarantine_interrupted().unwrap(), 0);
}
