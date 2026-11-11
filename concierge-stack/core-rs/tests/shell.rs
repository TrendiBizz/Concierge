//! End-to-end shell test with a fake internal API, a fake Grok websocket and a
//! fake Asterisk caller. No database, no network beyond loopback.

use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::{extract::State, routing::post, Json, Router};
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use concierge_core::shell::{packet, serve, Config, Route};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio_tungstenite::accept_async;
use tokio_tungstenite::tungstenite::Message;

type Calls = Arc<Mutex<Vec<String>>>;

async fn record(State(calls): State<Calls>, path: &str) -> Value {
    calls.lock().unwrap().push(path.to_string());
    match path {
        "/internal/voice/start" => json!({
            "tenant": {"id": "00000000-0000-0000-0000-000000000001", "name": "Test"},
            "conversation_id": "1",
            "record_session": {"id": "7", "recording_consent": false},
            "session": {"type": "realtime", "audio": {}},
        }),
        "/internal/voice/tool" => json!({"ok": true, "recording": true}),
        "/internal/voice/monitor" => json!({"telephone": true, "recording": true}),
        "/internal/voice/finish" => json!({"ok": true}),
        "/internal/voice/recording" => json!({"ok": true}),
        _ => json!({"ok": true}),
    }
}

async fn handler(
    State(calls): State<Calls>,
    headers: axum::http::HeaderMap,
    uri: axum::http::Uri,
    Json(_body): Json<Value>,
) -> Json<Value> {
    if headers
        .get("x-concierge-internal")
        .and_then(|v| v.to_str().ok())
        != Some("test-token")
    {
        return Json(json!({"error": "unauthorized"}));
    }
    Json(record(State(calls), uri.path()).await)
}

async fn fake_internal(calls: Calls) -> SocketAddr {
    let app = Router::new()
        .route("/internal/voice/start", post(handler))
        .route("/internal/voice/transcript", post(handler))
        .route("/internal/voice/tool", post(handler))
        .route("/internal/voice/monitor", post(handler))
        .route("/internal/voice/finish", post(handler))
        .route("/internal/voice/recording", post(handler))
        .with_state(calls);
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    addr
}

async fn fake_grok() -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        let (stream, _) = listener.accept().await.unwrap();
        let mut ws = accept_async(stream).await.unwrap();
        let _ = ws.next().await; // session.update
        ws.send(Message::Text(
            json!({"type": "session.updated"}).to_string().into(),
        ))
        .await
        .unwrap();
        let audio = STANDARD.encode(vec![1u8; 320]);
        ws.send(Message::Text(
            json!({"type": "response.audio.delta", "delta": audio})
                .to_string()
                .into(),
        ))
        .await
        .unwrap();
        ws.send(Message::Text(
            json!({"type": "conversation.item.input_audio_transcription.completed",
                   "item_id": "i1", "transcript": "hello"})
            .to_string()
            .into(),
        ))
        .await
        .unwrap();
        ws.send(Message::Text(
            json!({"type": "response.function_call_arguments.done", "call_id": "c1",
                   "name": "search_knowledge", "arguments": "{}"})
            .to_string()
            .into(),
        ))
        .await
        .unwrap();
        ws.send(Message::Text(
            json!({"type": "response.done"}).to_string().into(),
        ))
        .await
        .unwrap();
        // The shell emits the function_call_output only after response.done.
        for _ in 0..10 {
            match tokio::time::timeout(Duration::from_millis(500), ws.next()).await {
                Ok(Some(Ok(Message::Text(text)))) if text.contains("function_call_output") => break,
                Ok(Some(Ok(_))) => continue,
                _ => break,
            }
        }
        ws.send(Message::Text(
            json!({"type": "response.function_call_arguments.done", "call_id": "c2",
                   "name": "end_call", "arguments": "{}"})
            .to_string()
            .into(),
        ))
        .await
        .unwrap();
        ws.send(Message::Text(
            json!({"type": "response.done"}).to_string().into(),
        ))
        .await
        .unwrap();
        tokio::time::sleep(Duration::from_secs(3)).await;
    });
    addr
}

fn free_port() -> u16 {
    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    listener.local_addr().unwrap().port()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn shell_runs_one_call_end_to_end() {
    let calls: Calls = Arc::new(Mutex::new(Vec::new()));
    let api = fake_internal(calls.clone()).await;
    let grok = fake_grok().await;
    let port = free_port();
    let config = Config {
        bind: "127.0.0.1".into(),
        peers: vec!["127.0.0.1/32".parse().unwrap()],
        internal_url: format!("http://{api}"),
        internal_token: "test-token".into(),
        xai_key: "test-key".into(),
        xai_url: format!("ws://{grok}"),
        routes: vec![Route {
            tenant: "test".into(),
            number: "+6421000000".into(),
            port,
        }],
    };
    let server = tokio::spawn(async move { serve(Arc::new(config)).await });
    tokio::time::sleep(Duration::from_millis(100)).await;

    let mut caller = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
    caller.write_all(&packet(1, &[9u8; 16])).await.unwrap();
    tokio::time::sleep(Duration::from_millis(300)).await;
    caller.write_all(&packet(0x10, &[3u8; 320])).await.unwrap();

    let mut frame = vec![0u8; 256];
    let read = tokio::time::timeout(Duration::from_secs(3), caller.read(&mut frame)).await;
    assert!(
        matches!(read, Ok(Ok(n)) if n > 0),
        "expected an audio frame from the shell"
    );

    let finished = tokio::time::timeout(Duration::from_secs(6), async {
        loop {
            if calls
                .lock()
                .unwrap()
                .iter()
                .any(|p| p == "/internal/voice/finish")
            {
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    })
    .await;
    assert!(
        finished.is_ok(),
        "finish was not called; calls={:?}",
        calls.lock().unwrap()
    );

    let calls = calls.lock().unwrap().clone();
    assert!(calls.iter().any(|p| p == "/internal/voice/start"));
    assert!(calls.iter().any(|p| p == "/internal/voice/tool"));
    assert!(calls.iter().any(|p| p == "/internal/voice/transcript"));
    assert!(calls.iter().any(|p| p == "/internal/voice/finish"));
    server.abort();
}
