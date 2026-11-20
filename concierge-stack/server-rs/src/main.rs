//! `concierge-server`: binds the router built in the library. Configuration comes from the same environment names as the Python API.
use concierge_server::{app, Config, State};

#[tokio::main]
async fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if !args.is_empty() && args != ["--migrate-only"] {
        eprintln!("usage: concierge-server [--migrate-only]");
        std::process::exit(2);
    }
    let config = Config::from_env();
    let bind = std::env::var("BIND").unwrap_or_else(|_| "127.0.0.1:8001".into());
    let state = State::connect(config).await.expect("database connection");
    if args == ["--migrate-only"] {
        if let Err(e) = state.migrate().await {
            eprintln!("schema migration failed: {e}");
            std::process::exit(1);
        }
        eprintln!("schema migration complete");
        return;
    }
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind");
    eprintln!("concierge-server listening on {bind}");
    axum::serve(
        listener,
        app(state).into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .await
    .expect("serve");
}
