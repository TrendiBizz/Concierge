use concierge_social::model::{Post, Status};

fn post() -> Post {
    Post {
        id: "post-1".into(),
        customer_id: "customer-1".into(),
        content: "Original".into(),
        link: String::new(),
        hashtags: String::new(),
        account_ids: vec!["account-1".into()],
        media: vec![],
        status: Status::Draft,
        scheduled_at: None,
        revision: 1,
        approved_revision: None,
        attempts: 0,
        last_error: None,
        created_at: 1,
        updated_at: 1,
    }
}

#[test]
fn no_direct_draft_to_scheduled_or_publish() {
    assert!(!Status::Draft.can_move_to(Status::Scheduled));
    assert!(!Status::PendingApproval.can_move_to(Status::Scheduled));
    assert!(!Status::Scheduled.can_move_to(Status::Published));
    assert!(Status::Draft.can_move_to(Status::PendingApproval));
    assert!(Status::PendingApproval.can_move_to(Status::Approved));
    assert!(Status::Approved.can_move_to(Status::Scheduled));
}

#[test]
fn publish_requires_current_approval_and_due_time() {
    let mut p = post();
    p.status = Status::Scheduled;
    p.scheduled_at = Some(100);
    assert!(!p.may_publish(100));
    p.approved_revision = Some(1);
    assert!(!p.may_publish(99));
    assert!(p.may_publish(100));
    p.revision += 1;
    assert!(!p.may_publish(101));
}

#[test]
fn edited_post_loses_approval() {
    let mut p = post();
    p.status = Status::Scheduled;
    p.approved_revision = Some(1);
    p.scheduled_at = Some(100);
    p.edit("Changed".into(), 5).unwrap();
    assert_eq!(p.status, Status::Draft);
    assert_eq!(p.revision, 2);
    assert_eq!(p.approved_revision, None);
    assert_eq!(p.scheduled_at, None);
}

#[test]
fn published_post_cannot_be_edited() {
    let mut p = post();
    p.status = Status::Published;
    assert!(p.edit("Changed".into(), 10).is_err());
    assert_eq!(p.content, "Original");
}
