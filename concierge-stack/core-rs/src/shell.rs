//! Loopback shell around the pure `media_bridge` state machine.
//!
//! The shell owns what the state machine deliberately does not: the AudioSocket
//! TCP listeners, the Grok websocket, the 20 ms clock and the call's recording.
//! Database, permissions, CRM and tools stay in Python and are reached over the
//! private loopback API (`/internal/voice/*`) with a shared token.

use std::collections::HashSet;
use std::net::IpAddr;
use std::sync::Arc;
use std::time::{Duration, Instant};

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use futures_util::stream::SplitSink;
use futures_util::{SinkExt, StreamExt};
use ipnet::IpNet;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{connect_async, MaybeTlsStream, WebSocketStream};
use tracing::{info, warn};

use crate::media_bridge::{
    append_event, classify, silence, tool_output, Action, Bridge, Deframer, Inbound, OutputStep,
    MAX_SECONDS, READY_SECONDS,
};

type WsStream = WebSocketStream<MaybeTlsStream<TcpStream>>;
type WsSink = SplitSink<WsStream, Message>;

const AUDIO_KIND: u8 = 0x10;
const CALL_KIND: u8 = 1;
const TICK: Duration = Duration::from_millis(20);

#[derive(Debug, Clone, Deserialize)]
pub struct Route {
    pub tenant: String,
    pub number: String,
    pub port: u16,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub bind: String,
    pub peers: Vec<IpNet>,
    pub internal_url: String,
    pub internal_token: String,
    pub xai_key: String,
    pub xai_url: String,
    pub routes: Vec<Route>,
}

pub fn parse_routes(json_text: &str) -> Result<Vec<Route>, String> {
    let routes: Vec<Route> =
        serde_json::from_str(json_text).map_err(|_| "invalid routes JSON".to_string())?;
    if routes.is_empty() {
        return Err("at least one route is required".into());
    }
    let ports: HashSet<u16> = routes.iter().map(|r| r.port).collect();
    let numbers: HashSet<&str> = routes.iter().map(|r| r.number.as_str()).collect();
    if ports.len() != routes.len() || numbers.len() != routes.len() {
        return Err("routes need unique ports and numbers".into());
    }
    for route in &routes {
        let slug_ok = !route.tenant.is_empty()
            && route.tenant.len() <= 80
            && route
                .tenant
                .chars()
                .next()
                .is_some_and(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
            && route
                .tenant
                .chars()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-');
        let number_ok = route.number.starts_with('+')
            && (7..=15).contains(&route.number[1..].len())
            && route.number[1..].chars().all(|c| c.is_ascii_digit())
            && !route.number[1..].starts_with('0');
        if !slug_ok || !number_ok || route.port < 1024 {
            return Err("invalid route".into());
        }
    }
    Ok(routes)
}

pub fn parse_peers(text: &str) -> Result<Vec<IpNet>, String> {
    let peers: Vec<IpNet> = text
        .split(',')
        .map(|s| s.trim().parse::<IpNet>())
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| "invalid peer network".to_string())?;
    if peers.is_empty() {
        return Err("at least one peer network is required".into());
    }
    if peers.iter().any(|n| n.prefix_len() == 0) {
        return Err("unrestricted peer network is forbidden".into());
    }
    Ok(peers)
}

pub fn peer_allowed(peer: IpAddr, networks: &[IpNet]) -> bool {
    networks.iter().any(|n| n.contains(&peer))
}

/// One AudioSocket packet: 3-byte header (kind, big-endian length) + body.
pub fn packet(kind: u8, body: &[u8]) -> Vec<u8> {
    assert!(body.len() <= u16::MAX as usize);
    let mut out = Vec::with_capacity(3 + body.len());
    out.push(kind);
    out.extend_from_slice(&(body.len() as u16).to_be_bytes());
    out.extend_from_slice(body);
    out
}

/// Mono 16-bit PCM at 8 kHz, captured only while recording is enabled.
#[derive(Default)]
pub struct WavRecorder {
    pub enabled: bool,
    pcm: Vec<u8>,
}

impl WavRecorder {
    pub fn start(&mut self) {
        self.enabled = true;
    }

    pub fn discard(&mut self) {
        self.enabled = false;
        self.pcm.clear();
    }

    pub fn append(&mut self, frames: &[u8]) {
        if self.enabled && self.pcm.len() < 8000 * 2 * MAX_SECONDS as usize {
            self.pcm.extend_from_slice(frames);
        }
    }

    /// Wraps the captured PCM in a 44-byte WAV header; `None` when nothing was captured.
    pub fn finish(&self) -> Option<Vec<u8>> {
        if self.pcm.is_empty() {
            return None;
        }
        let data_len = self.pcm.len() as u32;
        let mut out = Vec::with_capacity(44 + self.pcm.len());
        out.extend_from_slice(b"RIFF");
        out.extend_from_slice(&(36 + data_len).to_le_bytes());
        out.extend_from_slice(b"WAVEfmt ");
        out.extend_from_slice(&16u32.to_le_bytes()); // PCM chunk size
        out.extend_from_slice(&1u16.to_le_bytes()); // PCM
        out.extend_from_slice(&1u16.to_le_bytes()); // mono
        out.extend_from_slice(&8000u32.to_le_bytes()); // sample rate
        out.extend_from_slice(&16000u32.to_le_bytes()); // byte rate
        out.extend_from_slice(&2u16.to_le_bytes()); // block align
        out.extend_from_slice(&16u16.to_le_bytes()); // bits per sample
        out.extend_from_slice(b"data");
        out.extend_from_slice(&data_len.to_le_bytes());
        out.extend_from_slice(&self.pcm);
        Some(out)
    }
}

#[derive(Debug, Deserialize)]
struct StartResponse {
    tenant: Value,
    conversation_id: i64,
    record_session: Value,
    session: Value,
}

/// The Python-owned side, reached over the private compose network.
#[derive(Clone)]
pub struct Internal {
    base: String,
    token: String,
    http: reqwest::Client,
}

impl Internal {
    pub fn new(base: String, token: String) -> Self {
        Self {
            base,
            token,
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(10))
                .build()
                .expect("http client"),
        }
    }

    async fn post(&self, path: &str, body: Value) -> Result<Value, String> {
        let url = format!("{}{}", self.base.trim_end_matches('/'), path);
        let response = self
            .http
            .post(url)
            .header("x-concierge-internal", &self.token)
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("internal {path}: {e}"))?;
        if !response.status().is_success() {
            return Err(format!("internal {path}: HTTP {}", response.status()));
        }
        response
            .json()
            .await
            .map_err(|e| format!("internal {path}: {e}"))
    }

    async fn start(
        &self,
        slug: &str,
        number: &str,
        call_id: &str,
    ) -> Result<StartResponse, String> {
        let value = self
            .post(
                "/internal/voice/start",
                json!({"slug": slug, "number": number, "call_id": call_id}),
            )
            .await?;
        serde_json::from_value(value).map_err(|e| format!("start response: {e}"))
    }
}

#[derive(Default)]
struct CallState {
    tenant_id: String,
    call_id: String,
    conversation: Option<i64>,
    record_id: Option<i64>,
    consent: bool,
}

async fn send_action(sink: &mut WsSink, action: Action) -> Result<(), String> {
    if let Action::Send(value) = action {
        sink.send(Message::Text(value.to_string().into()))
            .await
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

async fn apply_actions(
    actions: Vec<Action>,
    bridge: &mut Bridge,
    sink: &mut WsSink,
    internal: &Internal,
    state: &mut CallState,
    recorder: &mut WavRecorder,
) -> Result<(), String> {
    for action in actions {
        match action {
            Action::Send(value) => {
                sink.send(Message::Text(value.to_string().into()))
                    .await
                    .map_err(|e| e.to_string())?;
            }
            Action::Transcript {
                role,
                text,
                item_id,
            } => {
                let conversation = state.conversation.ok_or("transcript before start")?;
                internal
                    .post(
                        "/internal/voice/transcript",
                        json!({
                            "conversation_id": conversation,
                            "role": role.as_str(),
                            "text": text,
                            "item_id": item_id,
                        }),
                    )
                    .await
                    .map_err(|e| warn!("transcript lost: {e}"))
                    .ok();
            }
            Action::Tool {
                call_id,
                name,
                args,
            } => {
                let tool_name = name.as_str().unwrap_or("").to_string();
                let conversation = state.conversation.ok_or("tool before start")?;
                let record_id = state.record_id.ok_or("tool before recording session")?;
                let result = internal
                    .post(
                        "/internal/voice/tool",
                        json!({
                            "tenant_id": state.tenant_id,
                            "record_session_id": record_id,
                            "conversation_id": conversation,
                            "call_id": call_id,
                            "name": tool_name,
                            "args": Value::Object(args),
                        }),
                    )
                    .await
                    .map_err(|e| format!("tool {tool_name}: {e}"))?;
                if tool_name == "set_call_recording" {
                    let on = result
                        .get("recording")
                        .and_then(Value::as_bool)
                        .unwrap_or(false);
                    state.consent = on;
                    if on {
                        recorder.start();
                    } else {
                        recorder.discard();
                    }
                }
                let output = tool_output(&result);
                if !bridge.tool_result(&call_id, output) {
                    return Err("tool result arrived out of order".into());
                }
            }
        }
    }
    Ok(())
}

async fn run_call(
    stream: &mut TcpStream,
    route: &Route,
    config: &Config,
    internal: &Internal,
    state: &mut CallState,
    recorder: &mut WavRecorder,
) -> Result<&'static str, String> {
    let mut deframer = Deframer::default();
    let mut read_buf = [0u8; 4096];

    let (kind, body) = loop {
        if let Some(packet) = deframer.next_packet().map_err(|e| format!("{e:?}"))? {
            break packet;
        }
        let n = tokio::time::timeout(Duration::from_secs(5), stream.read(&mut read_buf))
            .await
            .map_err(|_| "call UUID timeout".to_string())?
            .map_err(|e| e.to_string())?;
        if n == 0 {
            return Err("disconnected before call UUID".into());
        }
        deframer.push(&read_buf[..n]);
    };
    if kind != CALL_KIND || body.len() != 16 {
        return Err("expected AudioSocket call UUID".into());
    }
    let call_id = format!(
        "ast:{}",
        uuid::Uuid::from_slice(&body).map_err(|e| e.to_string())?
    );
    state.call_id = call_id.clone();

    let start = internal
        .start(&route.tenant, &route.number, &call_id)
        .await?;
    state.tenant_id = start
        .tenant
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    state.conversation = Some(start.conversation_id);
    state.record_id = start.record_session.get("id").and_then(Value::as_i64);

    let mut request = config
        .xai_url
        .clone()
        .into_client_request()
        .map_err(|e| e.to_string())?;
    request.headers_mut().insert(
        "Authorization",
        format!("Bearer {}", config.xai_key)
            .parse()
            .map_err(|_| "invalid xAI key".to_string())?,
    );
    let (ws, _) = connect_async(request).await.map_err(|e| e.to_string())?;
    let (mut sink, mut source) = ws.split();

    let mut bridge = Bridge::new();
    let start_action = bridge.start(&start.session);
    send_action(&mut sink, start_action).await?;

    // Phase 1: no caller audio is read until Grok accepts the session.
    let ready_deadline = tokio::time::Instant::now() + Duration::from_secs(READY_SECONDS);
    while !bridge.ready {
        match tokio::time::timeout_at(ready_deadline, source.next()).await {
            Ok(Some(Ok(Message::Text(text)))) => {
                let actions = bridge
                    .on_message(text.as_str())
                    .map_err(|e| format!("{e:?}"))?;
                apply_actions(actions, &mut bridge, &mut sink, internal, state, recorder).await?;
            }
            Ok(Some(Ok(Message::Close(_)))) | Ok(None) => {
                return Err("Grok closed before session.updated".into());
            }
            Ok(Some(Ok(_))) => {}
            Ok(Some(Err(e))) => return Err(e.to_string()),
            Err(_) => return Err("Grok session was not ready in time".into()),
        }
    }

    let started = Instant::now();
    let mut ticker = tokio::time::interval(TICK);
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    ticker.tick().await;
    let mut monitor = tokio::time::interval(Duration::from_secs(5));
    monitor.tick().await;
    let mut status = "completed";

    loop {
        if started.elapsed() > Duration::from_secs(MAX_SECONDS) {
            break;
        }
        tokio::select! {
            biased;
            message = source.next() => {
                match message {
                    Some(Ok(Message::Text(text))) => {
                        let actions = bridge.on_message(text.as_str()).map_err(|e| format!("{e:?}"))?;
                        apply_actions(actions, &mut bridge, &mut sink, internal, state, recorder).await?;
                    }
                    Some(Ok(Message::Close(_))) | None => break,
                    Some(Ok(_)) => {}
                    Some(Err(e)) => return Err(e.to_string()),
                }
            }
            read = tokio::time::timeout(TICK, stream.read(&mut read_buf)) => {
                match read {
                    Ok(Ok(0)) => { status = "disconnected"; break; }
                    Ok(Ok(n)) => {
                        deframer.push(&read_buf[..n]);
                        let mut hangup = false;
                        while let Some((kind, body)) = deframer.next_packet().map_err(|e| format!("{e:?}"))? {
                            match classify(kind, &body).map_err(|e| format!("{e:?}"))? {
                                Inbound::Hangup => { hangup = true; break; }
                                Inbound::Audio => {
                                    recorder.append(&body);
                                    sink.send(Message::Text(append_event(&body).to_string().into()))
                                        .await.map_err(|e| e.to_string())?;
                                }
                                Inbound::Ignore => {}
                            }
                        }
                        if hangup { break; }
                    }
                    Ok(Err(e)) => return Err(e.to_string()),
                    Err(_) => {
                        let frame = silence();
                        recorder.append(&frame);
                        sink.send(Message::Text(append_event(&frame).to_string().into()))
                            .await.map_err(|e| e.to_string())?;
                    }
                }
            }
            _ = ticker.tick() => {
                match bridge.output_tick(started.elapsed().as_secs_f64()) {
                    OutputStep::Frame(frame) => {
                        recorder.append(&frame);
                        stream.write_all(&packet(AUDIO_KIND, &frame)).await.map_err(|e| e.to_string())?;
                    }
                    OutputStep::Finished => break,
                    OutputStep::Wait => {}
                }
            }
            _ = monitor.tick() => {
                match internal.post("/internal/voice/monitor", json!({
                    "tenant_id": state.tenant_id,
                    "record_session_id": state.record_id,
                })).await {
                    Ok(checks) => {
                        if checks.get("telephone").and_then(Value::as_bool) == Some(false) {
                            return Err("telephone authorization revoked".into());
                        }
                        if checks.get("recording").and_then(Value::as_bool) == Some(false) && recorder.enabled {
                            recorder.discard();
                            state.consent = false;
                        }
                    }
                    Err(e) => warn!("monitor check failed: {e}"),
                }
            }
        }
    }
    Ok(status)
}

async fn handle(mut stream: TcpStream, route: Route, config: Arc<Config>) {
    let mut state = CallState::default();
    let mut recorder = WavRecorder::default();
    let internal = Internal::new(config.internal_url.clone(), config.internal_token.clone());
    let status = match run_call(
        &mut stream,
        &route,
        &config,
        &internal,
        &mut state,
        &mut recorder,
    )
    .await
    {
        Ok(status) => status,
        Err(error) => {
            warn!("call ended: {error}");
            "failed"
        }
    };
    if let (Some(conversation), Some(record_id)) = (state.conversation, state.record_id) {
        if let Some(wav) = recorder.finish() {
            if state.consent {
                let _ = internal
                    .post(
                        "/internal/voice/recording",
                        json!({
                            "record_session_id": record_id,
                            "wav_b64": STANDARD.encode(&wav),
                        }),
                    )
                    .await;
            }
        }
        let _ = internal
            .post(
                "/internal/voice/finish",
                json!({
                    "tenant_id": state.tenant_id,
                    "call_id": state.call_id,
                    "conversation_id": conversation,
                    "status": status,
                    "record_session_id": record_id,
                }),
            )
            .await;
    }
    let _ = stream.shutdown().await;
}

/// Serve every configured route's private AudioSocket listener.
pub async fn serve(config: Arc<Config>) -> Result<(), String> {
    let mut tasks = Vec::new();
    for route in config.routes.clone() {
        let listener = TcpListener::bind(format!("{}:{}", config.bind, route.port))
            .await
            .map_err(|e| format!("bind {}:{}: {e}", config.bind, route.port))?;
        info!(
            "listening on {}:{} for {}",
            config.bind, route.port, route.tenant
        );
        let config = config.clone();
        tasks.push(tokio::spawn(async move {
            loop {
                match listener.accept().await {
                    Ok((stream, peer)) => {
                        if peer_allowed(peer.ip(), &config.peers) {
                            tokio::spawn(handle(stream, route.clone(), config.clone()));
                        } else {
                            warn!("rejected AudioSocket peer {}", peer.ip());
                        }
                    }
                    Err(error) => {
                        warn!("accept failed: {error}");
                        break;
                    }
                }
            }
        }));
    }
    for task in tasks {
        let _ = task.await;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn packet_roundtrip() {
        let bytes = packet(0x10, &[1, 2, 3]);
        assert_eq!(bytes, vec![0x10, 0, 3, 1, 2, 3]);
    }

    #[test]
    fn wav_header_and_data() {
        let mut recorder = WavRecorder::default();
        recorder.append(&[9u8; crate::media_bridge::FRAME_BYTES]); // ignored until recording starts
        assert!(recorder.finish().is_none());
        recorder.start();
        recorder.append(&[7u8; crate::media_bridge::FRAME_BYTES]);
        let wav = recorder.finish().expect("wav");
        assert_eq!(&wav[0..4], b"RIFF");
        assert_eq!(&wav[8..12], b"WAVE");
        assert_eq!(&wav[36..40], b"data");
        assert_eq!(wav.len(), 44 + crate::media_bridge::FRAME_BYTES);
    }

    #[test]
    fn routes_and_peers_validate() {
        let routes =
            parse_routes(r#"[{"tenant":"t1","number":"+6421000000","port":5101}]"#).unwrap();
        assert_eq!(routes.len(), 1);
        assert!(parse_routes("[]").is_err());
        assert!(parse_peers("127.0.0.1/32").is_ok());
        assert!(parse_peers("0.0.0.0/0").is_err());
        assert!(peer_allowed(
            "127.0.0.1".parse().unwrap(),
            &parse_peers("127.0.0.1/32").unwrap()
        ));
    }
}
