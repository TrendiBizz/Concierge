//! End-to-end shell test with a fake internal API, a fake Gemini 3.8 Live websocket and a
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
            "session": {"model": "models/gemini-3.8-live", "gemini_voice": "Aoede", "instructions": "Test business"},
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

async fn fake_gemini() -> SocketAddr {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        let (stream, _) = listener.accept().await.unwrap();
        let mut ws = accept_async(stream).await.unwrap();
        let first = ws.next().await.unwrap().unwrap();
        let setup: Value = serde_json::from_str(first.to_text().unwrap()).unwrap();
        assert_eq!(setup["setup"]["model"], "models/gemini-3.8-live");
        assert!(setup["setup"]["generationConfig"].get("thinkingConfig").is_none());

        ws.send(Message::Text(json!({"setupComplete": {}}).to_string().into()))
            .await
            .unwrap();

        // 24kHz PCM16 audio (960 bytes -> 320 bytes @ 8kHz)
        let audio24 = STANDARD.encode(vec![1u8; 960]);
        ws.send(Message::Text(
            json!({
                "serverContent": {
                    "modelTurn": {
                        "parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": audio24}}]
                    },
                    "inputTranscription": {"text": "hello", "finished": true},
                    "turnComplete": true
                }
            })
            .to_string()
            .into(),
        ))
        .await
        .unwrap();

        ws.send(Message::Text(
            json!({
                "toolCall": {
                    "functionCalls": [{"id": "c1", "name": "search_knowledge", "args": {}}]
                }
            })
            .to_string()
            .into(),
        ))
        .await
        .unwrap();

        for _ in 0..10 {
            match tokio::time::timeout(Duration::from_millis(500), ws.next()).await {
                Ok(Some(Ok(Message::Text(text)))) if text.contains("toolResponse") => break,
                Ok(Some(Ok(_))) => continue,
                _ => break,
            }
        }

        ws.send(Message::Text(
            json!({
                "toolCall": {
                    "functionCalls": [{"id": "c2", "name": "end_call", "args": {}}]
                }
            })
            .to_string()
            .into(),
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
    let gemini = fake_gemini().await;
    let port = free_port();
    let config = Config {
        bind: "127.0.0.1".into(),
        peers: vec!["127.0.0.1/32".parse().unwrap()],
        internal_url: format!("http://{api}"),
        internal_token: "test-token".into(),
        gemini_key: "test-key".into(),
        gemini_url: format!("ws://{gemini}"),
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
