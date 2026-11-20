//! `concierge-server`: binds the router built in the library. Configuration comes from the same environment names as the Python API.
use concierge_server::{app, Config, State};

#[tokio::main]
async fn main() {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if !args.is_empty()
        && !matches!(
            args.first().map(String::as_str),
            Some("--migrate-only" | "--purge-voice-once" | "--prune-owner-auth")
        )
    {
        eprintln!("usage: concierge-server [--migrate-only | --purge-voice-once | --prune-owner-auth [--apply] [--batch-size N]]");
        std::process::exit(2);
    }
    if args.first().is_some_and(|a| a == "--prune-owner-auth") {
        let mut batch = 500;
        let mut apply = false;
        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--apply" => apply = true,
                "--batch-size" => {
                    i += 1;
                    batch = args.get(i).and_then(|s| s.parse().ok()).unwrap_or(0);
                }
                _ => {
                    eprintln!("Unknown maintenance option");
                    std::process::exit(2);
                }
            }
            i += 1;
        }
        if let Err(e) = concierge_core::maintenance::check_batch_size(batch) {
            eprintln!("{e}");
            std::process::exit(2);
        }
        if std::env::var("DATABASE_URL")
            .ok()
            .is_none_or(|s| s.is_empty())
        {
            eprintln!("DATABASE_URL is required; no implicit production DB selection");
            std::process::exit(2);
        }
        let state = State::connect(Config::from_env())
            .await
            .expect("database connection");
        match concierge_server::maintenance::prune_auth(&state, batch, !apply).await {
            Ok(v) => println!("{v}"),
            Err(e) => {
                eprintln!("{e}");
                std::process::exit(1);
            }
        }
        return;
    }
    if args.len() > 1 {
        eprintln!("Unexpected arguments");
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
    if args == ["--purge-voice-once"] {
        if let Err(e) = concierge_server::maintenance::purge_voice(&state).await {
            eprintln!("{e}");
            std::process::exit(1);
        }
        return;
    }
    let (stop_tx, stop_rx) = tokio::sync::watch::channel(false);
    let worker = tokio::spawn(concierge_server::maintenance::voice_worker(
        state.clone(),
        stop_rx,
        std::time::Duration::from_secs(3600),
    ));
    let listener = tokio::net::TcpListener::bind(&bind).await.expect("bind");
    eprintln!("concierge-server listening on {bind}");
    axum::serve(
        listener,
        app(state).into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .with_graceful_shutdown(async move {
        let _ = tokio::signal::ctrl_c().await;
        let _ = stop_tx.send(true);
    })
    .await
    .expect("serve");
    worker.await.expect("retention worker");
}
