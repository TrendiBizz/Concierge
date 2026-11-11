//! Private AudioSocket → Grok telephone shell. The Python bridge remains the
//! fallback and the only bridge answering calls until cut-over.
use std::sync::Arc;

use concierge_core::shell::{parse_peers, parse_routes, serve, Config};

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_max_level(tracing::Level::INFO)
        .init();

    let routes = std::env::var("ASTERISK_ROUTES").expect("ASTERISK_ROUTES");
    let config = Config {
        bind: std::env::var("ASTERISK_BIND").unwrap_or_else(|_| "127.0.0.1".into()),
        peers: parse_peers(
            &std::env::var("ASTERISK_PEERS").unwrap_or_else(|_| "127.0.0.1/32,::1/128".into()),
        )
        .expect("ASTERISK_PEERS"),
        internal_url: std::env::var("CONCIERGE_INTERNAL_URL")
            .unwrap_or_else(|_| "http://api:8000".into()),
        internal_token: std::env::var("CONCIERGE_INTERNAL_TOKEN")
            .expect("CONCIERGE_INTERNAL_TOKEN"),
        xai_key: std::env::var("XAI_API_KEY").expect("XAI_API_KEY"),
        xai_url: std::env::var("XAI_REALTIME_URL")
            .unwrap_or_else(|_| "wss://api.x.ai/v1/realtime".into()),
        routes: parse_routes(&routes).expect("ASTERISK_ROUTES"),
    };
    if let Err(error) = serve(Arc::new(config)).await {
        eprintln!("asterisk shell failed: {error}");
        std::process::exit(1);
    }
}
