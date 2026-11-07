//! Local-only server. No public listener, no network connector enabled by default.
use concierge_social::{
    api::{router, AppState},
    store::Store,
    vault::Vault,
};
use std::sync::Arc;
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let concierge = std::env::var("SOCIAL_CONCIERGE_KEY")?;
    let agent = std::env::var("SOCIAL_AGENT_KEY")?;
    if concierge.len() < 32 || agent.len() < 32 || concierge == agent {
        return Err("Distinct long service keys (32+ chars) are required".into());
    }
    let vault = Arc::new(Vault::from_base64_key(&std::env::var("SOCIAL_VAULT_KEY")?)?);
    let db = std::env::var("SOCIAL_DB").unwrap_or_else(|_| "./data/social.db".into());
    if let Some(dir) = std::path::Path::new(&db).parent() {
        std::fs::create_dir_all(dir)?;
    }
    let store = Arc::new(Store::open(&db)?);
    let interrupted = store.quarantine_interrupted()?;
    if interrupted > 0 {
        eprintln!("Quarantined {interrupted} interrupted social posts for manual reconciliation");
    }

    let bind = std::env::var("SOCIAL_BIND").unwrap_or_else(|_| "127.0.0.1:4390".into());
    let address: std::net::SocketAddr = bind.parse()?;
    if !address.ip().is_loopback() {
        return Err("Social API must bind to loopback only".into());
    }
    // An explicit, separate switch is required for any network publishing.
    // The default service can safely handle drafts and approvals offline.
    if std::env::var("SOCIAL_ENABLE_PUBLISH").as_deref() == Ok("true") {
        let store_for_scheduler = store.clone();
        let vault_for_scheduler = vault.clone();
        let mut registry = concierge_social::connector::Registry::new();
        registry.register(Arc::new(concierge_social::bluesky::Bluesky::new()));
        // Every new platform requires its own operator switch in addition
        // to the global publishing switch, preventing accidental posting.
        if std::env::var("SOCIAL_ENABLE_MASTODON_PUBLISH").as_deref() == Ok("true") {
            let origin = std::env::var("SOCIAL_MASTODON_ORIGIN")?;
            registry.register(Arc::new(concierge_social::social_publish::Mastodon::new(
                &origin,
            )?));
        }
        if std::env::var("SOCIAL_ENABLE_LINKEDIN_PUBLISH").as_deref() == Ok("true") {
            let version =
                std::env::var("SOCIAL_LINKEDIN_API_VERSION").unwrap_or_else(|_| "202603".into());
            registry.register(Arc::new(concierge_social::social_publish::LinkedIn::new(
                &version,
            )?));
        }
        tokio::spawn(async move {
            loop {
                let now = time::OffsetDateTime::now_utc().unix_timestamp();
                if let Err(error) = concierge_social::scheduler::run_due(
                    &store_for_scheduler,
                    &vault_for_scheduler,
                    &registry,
                    now,
                )
                .await
                {
                    eprintln!("Social scheduler cycle failed: {error}");
                }
                tokio::time::sleep(std::time::Duration::from_secs(15)).await;
            }
        });
    }
    let app = router(AppState {
        store,
        vault,
        concierge_key: concierge,
        agent_key: agent,
    });
    let listener = tokio::net::TcpListener::bind(address).await?;
    println!(
        "Concierge social API listening locally on {}",
        listener.local_addr()?
    );
    axum::serve(listener, app).await?;
    Ok(())
}
