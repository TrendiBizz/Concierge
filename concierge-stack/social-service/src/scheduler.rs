//! Delivers only current-revision customer-approved posts.
//! Never blindly retries a request if the outcome could have been accepted remotely.
use crate::connector::{ConnectorError, PublishRequest, Registry};
use crate::model::Status;
use crate::store::Store;
use crate::vault::{account_label, Vault};
use sha2::{Digest, Sha256};

pub async fn run_due(
    store: &Store,
    vault: &Vault,
    registry: &Registry,
    now: i64,
) -> Result<usize, String> {
    let due = store.claim_due(now)?;
    let mut done = 0;
    for post in due {
        if post.approved_revision != Some(post.revision) {
            store.finish(
                &post.customer_id,
                &post.id,
                Status::Failed,
                Some("Approved revision mismatch".into()),
                None,
            )?;
            continue;
        }
        // The customer's rules may have changed since approval; check again
        // before any network request, using only this tenant's account IDs.
        let current_rules = store.rules(&post.customer_id)?;
        let mut networks = Vec::new();
        let mut valid_accounts = true;
        for account_id in &post.account_ids {
            // Renew provider credentials before claiming the post is publishable.
            // This only runs for an already-approved scheduled post while the
            // separately authorized live publishing scheduler is enabled.
            if let Ok((network, _, _, _, expiry)) =
                store.refresh_candidate(&post.customer_id, account_id)
            {
                if matches!(
                    network.as_str(),
                    "instagram" | "linkedin" | "google_business"
                ) && expiry.is_some_and(|deadline| deadline <= now + 7 * 86400)
                    && crate::token_refresh::refresh(store, vault, &post.customer_id, account_id)
                        .await
                        .is_err()
                {
                    valid_accounts = false;
                    break;
                }
            }
            match store.account(&post.customer_id, account_id) {
                Ok((network, _, _, _)) => networks.push(network),
                Err(_) => {
                    valid_accounts = false;
                    break;
                }
            }
        }
        if !valid_accounts {
            store.finish(
                &post.customer_id,
                &post.id,
                Status::Failed,
                Some("Approved account is unavailable or requires reconnection".into()),
                None,
            )?;
            continue;
        }
        let check = crate::guardrails::check_post(
            &crate::guardrails::PostInput {
                content: post.content.clone(),
                link: post.link.clone(),
                hashtags: post.hashtags.clone(),
                networks,
                media_count: post.media.len(),
            },
            &current_rules,
        );
        if !check.ok {
            store.finish(
                &post.customer_id,
                &post.id,
                Status::Failed,
                Some("Current customer posting rules reject the approved content".into()),
                None,
            )?;
            continue;
        }
        let mut failed = None;
        let mut retryable = false;
        for account_id in &post.account_ids {
            if store.result_exists(&post.id, account_id)? {
                continue;
            }
            let (network, external_id, sealed, refresh) =
                match store.account(&post.customer_id, account_id) {
                    Ok(a) => a,
                    Err(e) => {
                        failed = Some(e);
                        break;
                    }
                };
            // OIDC account linking does not authorize posting. Check the actual
            // tenant-bound grant even if LinkedIn publishing is later enabled.
            if network == "linkedin"
                && !store.account_has_scope(&post.customer_id, account_id, "w_member_social")?
            {
                failed = Some("LinkedIn account has not authorized publishing".into());
                break;
            }
            let label = account_label(&post.customer_id, &network, &external_id);
            let access = vault.open(&sealed, &label)?;
            let refresh = refresh.map(|v| vault.open(&v, &label)).transpose()?;
            let Some(connector) = registry.get(&network) else {
                failed = Some(format!("No connector for {network}"));
                break;
            };
            let idempotency_key = format!(
                "{:x}",
                Sha256::digest(
                    format!(
                        "{}:{}:{}:{}",
                        post.customer_id, post.id, post.revision, account_id
                    )
                    .as_bytes()
                )
            );
            let request = PublishRequest {
                external_id,
                idempotency_key,
                access_token: access,
                refresh_token: refresh,
                text: [
                    post.content.as_str(),
                    post.link.as_str(),
                    post.hashtags.as_str(),
                ]
                .into_iter()
                .filter(|part| !part.trim().is_empty())
                .collect::<Vec<_>>()
                .join("\n"),
                link: post.link.clone(),
                media: post.media.clone(),
            };
            match connector.publish(request).await {
                Ok(result) => {
                    store.record_result(
                        &post.id,
                        account_id,
                        true,
                        Some(&result.external_id),
                        None,
                    )?;
                }
                Err(ConnectorError::AuthExpired(reason)) => {
                    store.mark_reauth(&post.customer_id, account_id)?;
                    failed = Some(reason);
                    break;
                }
                Err(ConnectorError::Permanent(reason)) => {
                    failed = Some(reason);
                    break;
                }
                Err(ConnectorError::Retryable(reason)) => {
                    // An ambiguous timeout may already have published. Treat as failed for
                    // manual reconciliation rather than risk a duplicate customer post.
                    failed = Some(reason);
                    retryable = true;
                    break;
                }
            }
        }
        if let Some(reason) = failed {
            // Explicitly do NOT automatically retry ambiguous errors.
            // A later approved revision may be submitted after reconciliation.
            let detail = if retryable {
                format!("Reconciliation required: {reason}")
            } else {
                reason
            };
            store.finish(
                &post.customer_id,
                &post.id,
                Status::Failed,
                Some(detail),
                None,
            )?;
        } else {
            store.finish(&post.customer_id, &post.id, Status::Published, None, None)?;
            done += 1;
        }
    }
    Ok(done)
}
