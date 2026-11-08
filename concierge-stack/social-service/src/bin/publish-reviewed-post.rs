//! Operator-only delivery of one explicitly selected approved post; no scheduler.
use concierge_social::{
    connector::Registry,
    meta_publish::{Facebook, Instagram},
    store::Store,
    vault::Vault,
};
use std::sync::Arc;
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::var("SOCIAL_ENABLE_PUBLISH").as_deref() != Ok("true") {
        return Err("Explicit publishing authorization is required".into());
    }
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 3 {
        return Err("Usage: publish-reviewed-post CUSTOMER POST_ID".into());
    }
    let store = Store::open(&std::env::var("SOCIAL_DB")?)?;
    let vault = Vault::from_base64_key(&std::env::var("SOCIAL_VAULT_KEY")?)?;
    let mut registry = Registry::new();
    registry.register(Arc::new(Facebook::new(
        &std::env::var("SOCIAL_META_GRAPH_VERSION").unwrap_or_else(|_| "v27.0".into()),
    )?));
    registry.register(Arc::new(Instagram::new()));
    concierge_social::scheduler::run_one(
        &store,
        &vault,
        &registry,
        concierge_social::now_unix(),
        &args[1],
        &args[2],
    )
    .await?;
    let post = store.get_post(&args[1], &args[2])?;
    println!("Selected post delivery state: {:?}", post.status);
    if post.status == concierge_social::model::Status::Failed {
        return Err(post
            .last_error
            .unwrap_or_else(|| "Selected post failed".into())
            .into());
    }
    Ok(())
}
