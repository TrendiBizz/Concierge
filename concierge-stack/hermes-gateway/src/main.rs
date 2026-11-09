//! Local-only server: loopback bind, long distinct keys, nothing enabled by default.
use hermes_gateway::backend::HttpBackend;
use hermes_gateway::ledger::MemoryLedger;
use hermes_gateway::server::{router, system_clock, AppState};
use std::collections::HashSet;
use std::sync::{Arc, Mutex};

fn need(name: &str) -> Result<String, Box<dyn std::error::Error>> {
    std::env::var(name).map_err(|_| format!("{name} is required").into())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let secret = need("HERMES_CAPABILITY_SECRET")?;
    let mint_key = need("HERMES_MINT_KEY")?;
    let concierge_key = need("HERMES_CONCIERGE_KEY")?;
    let distinct = secret != mint_key && secret != concierge_key && mint_key != concierge_key;
    if secret.len() < 32 || mint_key.len() < 32 || concierge_key.len() < 32 || !distinct {
        return Err("Three distinct keys of 32+ characters are required (capability secret, mint key, Concierge key)".into());
    }
    let base =
        std::env::var("CONCIERGE_BASE_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let bind = std::env::var("HERMES_GATEWAY_BIND").unwrap_or_else(|_| "127.0.0.1:4420".into());
    let address: std::net::SocketAddr = bind.parse()?;
    if !address.ip().is_loopback() {
        return Err("The Hermes gateway must bind to loopback only".into());
    }
    let state = Arc::new(AppState {
        secret: secret.into_bytes(),
        mint_key,
        backend: Arc::new(HttpBackend::new(&base, &concierge_key)?),
        revoked: Mutex::new(HashSet::new()),
        ledger: Mutex::new(MemoryLedger::default()),
        clock: system_clock(),
    });
    let listener = tokio::net::TcpListener::bind(address).await?;
    eprintln!("hermes-gateway listening on {address}, Concierge at {base}");
    axum::serve(listener, router(state))
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
