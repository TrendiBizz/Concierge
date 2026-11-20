//! Local-only server: loopback bind, long distinct keys, nothing enabled by default.
use action_gateway::backend::HttpBackend;
use action_gateway::ledger::MemoryLedger;
use action_gateway::orchestrator::ModelHttp;
use action_gateway::server::{router, system_clock, AppState};
use std::collections::HashSet;
use std::sync::{Arc, Mutex};

fn need(name: &str) -> Result<String, Box<dyn std::error::Error>> {
    std::env::var(name).map_err(|_| format!("{name} is required").into())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let secret = need("ACTION_CAPABILITY_SECRET")?;
    let mint_key = need("ACTION_MINT_KEY")?;
    let concierge_key = need("ACTION_CONCIERGE_KEY")?;
    let distinct = secret != mint_key && secret != concierge_key && mint_key != concierge_key;
    if secret.len() < 32 || mint_key.len() < 32 || concierge_key.len() < 32 || !distinct {
        return Err("Three distinct keys of 32+ characters are required (capability secret, mint key, Concierge key)".into());
    }
    let model_key = need("PLANNER_API_KEY")?;
    let model_base = need("PLANNER_BASE_URL")?;
    let model = need("PLANNER_MODEL")?;
    let base =
        std::env::var("CONCIERGE_BASE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let bind = std::env::var("ACTION_GATEWAY_BIND").unwrap_or_else(|_| "127.0.0.1:4420".into());
    let address: std::net::SocketAddr = bind.parse()?;
    if !address.ip().is_loopback() {
        return Err("The Concierge gateway must bind to loopback only".into());
    }
    let state = Arc::new(AppState {
        secret: secret.into_bytes(),
        mint_key,
        backend: Arc::new(HttpBackend::new(&base, &concierge_key)?),
        planner: Arc::new(ModelHttp::new(&model_base, &model_key, &model)?),
        revoked: Mutex::new(HashSet::new()),
        ledger: Mutex::new(MemoryLedger::default()),
        clock: system_clock(),
    });
    let listener = tokio::net::TcpListener::bind(address).await?;
    eprintln!("action-gateway listening on {address}, Concierge at {base}");
    axum::serve(listener, router(state))
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
