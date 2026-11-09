//! `concierge-server`: binds the router built in the library. Configuration comes from the same environment names as the Python API.
use concierge_server::{app, Config, State};

#[tokio::main]
async fn main() {
    let config = Config::from_env();
    let bind = std::env::var("BIND").unwrap_or_else(|_| "127.0.0.1:8001".into());
    let state = State::connect(config).await.expect("database connection");
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind");
    eprintln!("concierge-server listening on {bind}");
    axum::serve(listener, app(state)).await.expect("serve");
}
