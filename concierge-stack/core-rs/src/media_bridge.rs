//! The telephone media bridge as a pure state machine (port of `asterisk_bridge.MediaBridge` for
//! Google Gemini 3.8 Live: setup payload, 8k↔16k/24k PCM16 resampling, Gemini Live event handler,
//! playback pacer and AudioSocket input rules).
use crate::pbx;
use crate::pyjson;
use base64::engine::general_purpose::{GeneralPurpose, GeneralPurposeConfig, STANDARD};
use base64::engine::DecodePaddingMode;
use base64::{alphabet, Engine};
use serde_json::{json, Map, Value};
use std::collections::{HashMap, HashSet, VecDeque};

/// 20 ms of 16-bit mono audio at 8 kHz, the native AudioSocket frame.
pub const FRAME_BYTES: usize = 320;
/// Seconds between frames in both directions.
pub const FRAME_SECONDS: f64 = 0.02;
/// A call is cut off after this many seconds.
pub const MAX_SECONDS: u64 = 600;
/// Seconds to wait for Gemini Live to accept the session before any caller audio is read.
pub const READY_SECONDS: u64 = 15;
/// Seconds of silence, after `end_call` and the last audio, before the line is released.
pub const LINGER_SECONDS: f64 = 0.4;
/// Thirty seconds of queued 8 kHz speech; more than this ends the call.
pub const PLAYBACK_LIMIT: usize = 16000 * 30;
/// Tool calls allowed in one call.
pub const TOOL_LIMIT: usize = 40;
/// Consecutive protocol errors before ending a call.
pub const MAX_ERRORS: usize = 5;
/// Telephone end-of-turn silence window (ms).
pub const SILENCE_DURATION_MS: u64 = 700;
const TRANSCRIPT_CHARS: usize = 10000;
const CALL_ID_CHARS: usize = 200;
const DEFAULT_GEMINI_MODEL: &str = "models/gemini-3.8-live";
const DEFAULT_GEMINI_VOICE: &str = "Aoede";
const GEMINI_VOICES: &[&str] = &[
    "Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Zephyr",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BridgeError {
    Json,
    NotObject,
    Key,
    Type,
    Base64,
    Value(&'static str),
    Runtime(&'static str),
    IncompleteRead,
    Unsupported(&'static str),
}

impl BridgeError {
    pub fn class(&self) -> String {
        match self {
            Self::Json => "json".into(),
            Self::NotObject => "not_object".into(),
            Self::Key => "key".into(),
            Self::Type => "type".into(),
            Self::Base64 => "base64".into(),
            Self::Value(m) => format!("value:{m}"),
            Self::Runtime(m) => format!("runtime:{m}"),
            Self::IncompleteRead => "incomplete".into(),
            Self::Unsupported(m) => format!("unsupported:{m}"),
        }
    }
}

impl std::fmt::Display for BridgeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.class())
    }
}

impl std::error::Error for BridgeError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Role {
    User,
    Assistant,
}

impl Role {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::User => "user",
            Self::Assistant => "assistant",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub enum Action {
    /// Send this JSON to Gemini Live.
    Send(Value),
    /// Store this turn. With an `item_id`, a later transcript for the same id and role replaces the stored text.
    Transcript {
        role: Role,
        text: String,
        item_id: Option<String>,
    },
    /// Run this tool, then call [`Bridge::tool_result`] with its output.
    Tool {
        call_id: String,
        name: Value,
        args: Map<String, Value>,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OutputStep {
    Frame(Vec<u8>),
    Wait,
    Finished,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Inbound {
    Hangup,
    Audio,
    Ignore,
}

pub fn decode_audio(text: &str) -> Result<Vec<u8>, BridgeError> {
    const ENGINE: GeneralPurpose = GeneralPurpose::new(
        &alphabet::STANDARD,
        GeneralPurposeConfig::new()
            .with_decode_allow_trailing_bits(true)
            .with_decode_padding_mode(DecodePaddingMode::RequireCanonical),
    );
    ENGINE.decode(text).map_err(|_| BridgeError::Base64)
}

/// Upsample 8 kHz PCM16 LE mono to 16 kHz PCM16 LE mono via 2x linear interpolation.
pub fn upsample_8k_to_16k(pcm: &[u8]) -> Result<Vec<u8>, BridgeError> {
    if !pcm.len().is_multiple_of(2) {
        return Err(BridgeError::Value("Invalid PCM16 frame"));
    }
    if pcm.is_empty() {
        return Ok(Vec::new());
    }
    let samples: Vec<i16> = pcm
        .chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect();
    let n = samples.len();
    let mut out = Vec::with_capacity(n * 4);
    for i in 0..n - 1 {
        let s0 = samples[i];
        let mid = ((s0 as i32 + samples[i + 1] as i32) >> 1) as i16;
        out.extend_from_slice(&s0.to_le_bytes());
        out.extend_from_slice(&mid.to_le_bytes());
    }
    let last = samples[n - 1];
    out.extend_from_slice(&last.to_le_bytes());
    out.extend_from_slice(&last.to_le_bytes());
    Ok(out)
}

/// Downsample 24 kHz PCM16 LE mono to 8 kHz PCM16 LE mono via 3:1 boxcar averaging.
pub fn downsample_24k_to_8k(pcm: &[u8]) -> Result<Vec<u8>, BridgeError> {
    if !pcm.len().is_multiple_of(2) {
        return Err(BridgeError::Value("Invalid PCM16 frame"));
    }
    let usable = (pcm.len() / 6) * 6;
    if usable == 0 {
        return Ok(Vec::new());
    }
    let samples: Vec<i16> = pcm[..usable]
        .chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect();
    let mut out = Vec::with_capacity((samples.len() / 3) * 2);
    for chunk in samples.chunks_exact(3) {
        let avg = ((chunk[0] as i32 + chunk[1] as i32 + chunk[2] as i32) / 3) as i16;
        out.extend_from_slice(&avg.to_le_bytes());
    }
    Ok(out)
}

pub fn strip_additional_properties(value: &Value) -> Value {
    match value {
        Value::Object(map) => {
            let mut out = Map::new();
            for (k, v) in map {
                if k != "additionalProperties" {
                    out.insert(k.clone(), strip_additional_properties(v));
                }
            }
            Value::Object(out)
        }
        Value::Array(items) => Value::Array(items.iter().map(strip_additional_properties).collect()),
        other => other.clone(),
    }
}

fn gemini_function_declarations(tools: Option<&Value>) -> Vec<Value> {
    let Some(Value::Array(list)) = tools else {
        return Vec::new();
    };
    let mut decls = Vec::new();
    for tool in list {
        let Some(obj) = tool.as_object() else {
            continue;
        };
        let Some(name) = obj.get("name").and_then(Value::as_str).filter(|s| !s.is_empty()) else {
            continue;
        };
        let mut decl = Map::new();
        decl.insert("name".into(), Value::String(name.to_string()));
        decl.insert(
            "description".into(),
            Value::String(
                obj.get("description")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            ),
        );
        if let Some(params) = obj.get("parameters") {
            let cleaned = strip_additional_properties(params);
            if cleaned
                .get("properties")
                .and_then(Value::as_object)
                .is_some_and(|p| !p.is_empty())
            {
                decl.insert("parameters".into(), cleaned);
            }
        }
        decls.push(Value::Object(decl));
    }
    decls
}

pub fn tool_output(result: &Value) -> String {
    pyjson::dumps(result).unwrap_or_else(|| result.to_string())
}

pub fn classify(kind: u8, body: &[u8]) -> Result<Inbound, BridgeError> {
    match kind {
        0 => Ok(Inbound::Hangup),
        0x10 if body.is_empty() || !body.len().is_multiple_of(2) => {
            Err(BridgeError::Value("Invalid PCM16 frame"))
        }
        0x10 => Ok(Inbound::Audio),
        3 if body.len() == 1 => Ok(Inbound::Ignore),
        _ => Err(BridgeError::Value("Unexpected AudioSocket frame")),
    }
}

/// The Gemini Live `realtimeInput` message that carries 16 kHz upsampled caller audio.
pub fn append_event(body: &[u8]) -> Value {
    let pcm16 = upsample_8k_to_16k(body).unwrap_or_default();
    json!({
        "realtimeInput": {
            "audio": {
                "data": STANDARD.encode(pcm16),
                "mimeType": "audio/pcm;rate=16000",
            }
        }
    })
}

pub fn silence() -> Vec<u8> {
    vec![0; FRAME_BYTES]
}

pub fn pace(started: f64, now: f64) -> f64 {
    let rest = FRAME_SECONDS - (now - started);
    if rest > 0.0 {
        rest
    } else {
        0.0
    }
}

#[derive(Default)]
pub struct Deframer {
    buffer: Vec<u8>,
}

impl Deframer {
    pub fn push(&mut self, bytes: &[u8]) {
        self.buffer.extend_from_slice(bytes);
    }

    pub fn next_packet(&mut self) -> Result<Option<(u8, Vec<u8>)>, BridgeError> {
        if self.buffer.len() < 3 {
            return Ok(None);
        }
        let (kind, length) = pbx::parse_header([self.buffer[0], self.buffer[1], self.buffer[2]])
            .map_err(BridgeError::Value)?;
        if self.buffer.len() < 3 + length {
            return Ok(None);
        }
        let body = self.buffer[3..3 + length].to_vec();
        self.buffer.drain(..3 + length);
        Ok(Some((kind, body)))
    }

    pub fn end_of_stream(&self) -> BridgeError {
        BridgeError::IncompleteRead
    }
}

pub struct Bridge {
    pub playback: VecDeque<u8>,
    pub ready: bool,
    pub ending: bool,
    pub speaking: bool,
    pub idle_since: Option<f64>,
    pcm24_rem: Vec<u8>,
    errors: usize,
    user_turn: usize,
    user_text: String,
    assistant_turn: usize,
    assistant_text: String,
    seen_transcripts: HashMap<(String, Role), String>,
    seen_tools: HashSet<String>,
}

impl Default for Bridge {
    fn default() -> Self {
        Self {
            playback: VecDeque::new(),
            ready: false,
            ending: false,
            speaking: false,
            idle_since: None,
            pcm24_rem: Vec::new(),
            errors: 0,
            user_turn: 1,
            user_text: String::new(),
            assistant_turn: 1,
            assistant_text: String::new(),
            seen_transcripts: HashMap::new(),
            seen_tools: HashSet::new(),
        }
    }
}

impl Bridge {
    pub fn new() -> Self {
        Self::default()
    }

    /// Build the Gemini 3.8 Live `setup` payload from the prepared session object.
    pub fn start(&self, session: &Value) -> Action {
        let model = session
            .get("model")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .unwrap_or(DEFAULT_GEMINI_MODEL);
        let requested_voice = session
            .get("gemini_voice")
            .or_else(|| session.get("voice"))
            .and_then(Value::as_str)
            .unwrap_or(DEFAULT_GEMINI_VOICE);
        let voice_name = if GEMINI_VOICES.contains(&requested_voice) {
            requested_voice
        } else {
            DEFAULT_GEMINI_VOICE
        };
        let mut generation_config = json!({
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name},
                }
            }
        });
        if let Some(level) = session
            .get("thinking_level")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
        {
            generation_config["thinkingConfig"] = json!({"thinkingLevel": level});
        }
        let mut setup = json!({
            "model": model,
            "generationConfig": generation_config,
            "realtimeInputConfig": {
                "automaticActivityDetection": {
                    "prefixPaddingMs": 300,
                    "silenceDurationMs": SILENCE_DURATION_MS,
                },
                "activityHandling": "START_OF_ACTIVITY_INTERRUPTS",
            },
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            "contextWindowCompression": {"slidingWindow": {}},
        });
        if let Some(instructions) = session
            .get("instructions")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
        {
            setup["systemInstruction"] = json!({"parts": [{"text": instructions}]});
        }
        let declarations = gemini_function_declarations(session.get("tools"));
        if !declarations.is_empty() {
            setup["tools"] = json!([{"functionDeclarations": declarations}]);
        }
        Action::Send(json!({"setup": setup}))
    }

    /// Build a Gemini Live `toolResponse` message for completed tool calls.
    pub fn tool_response(responses: Vec<Value>) -> Action {
        Action::Send(json!({"toolResponse": {"functionResponses": responses}}))
    }

    fn emit_transcript(&mut self, role: Role, item_id: String, text: &str, actions: &mut Vec<Action>) {
        if text.trim().is_empty() {
            return;
        }
        let key = (item_id.clone(), role);
        if self.seen_transcripts.get(&key).map(String::as_str) == Some(text) {
            return;
        }
        self.seen_transcripts.insert(key, text.to_string());
        actions.push(Action::Transcript {
            role,
            text: text.chars().take(TRANSCRIPT_CHARS).collect(),
            item_id: Some(item_id),
        });
    }

    fn finish_user_turn(&mut self) {
        if !self.user_text.is_empty() {
            self.user_turn += 1;
            self.user_text.clear();
        }
    }

    fn finish_assistant_turn(&mut self) {
        if !self.assistant_text.is_empty() {
            self.assistant_turn += 1;
            self.assistant_text.clear();
        }
    }

    /// Process one WebSocket message from Gemini Live.
    pub fn on_message(&mut self, text: &str) -> Result<Vec<Action>, BridgeError> {
        let parsed: Value = serde_json::from_str(text).map_err(|_| BridgeError::Json)?;
        let event = parsed.as_object().ok_or(BridgeError::NotObject)?;
        let mut actions = Vec::new();

        if event.contains_key("setupComplete") {
            if !self.ready {
                self.ready = true;
                actions.push(Action::Send(json!({
                    "clientContent": {
                        "turns": [{
                            "role": "user",
                            "parts": [{"text": "A caller has just connected. Greet them now."}],
                        }],
                        "turnComplete": true,
                    }
                })));
            }
            return Ok(actions);
        }

        if event.contains_key("error") {
            self.errors += 1;
            if self.errors >= MAX_ERRORS {
                return Err(BridgeError::Runtime("Gemini Live rejected telephone session"));
            }
            return Ok(actions);
        }

        if event.contains_key("goAway") {
            return Ok(actions);
        }

        if let Some(sc) = event.get("serverContent").and_then(Value::as_object) {
            if sc.get("interrupted").and_then(Value::as_bool) == Some(true) {
                self.playback.clear();
                self.pcm24_rem.clear();
                self.speaking = false;
                self.ending = false;
                self.finish_assistant_turn();
            }

            if let Some(in_tx) = sc.get("inputTranscription").and_then(Value::as_object) {
                if let Some(chunk) = in_tx.get("text").and_then(Value::as_str).filter(|s| !s.is_empty()) {
                    self.finish_assistant_turn();
                    self.user_text.push_str(chunk);
                    let id = format!("user-{}", self.user_turn);
                    let current = self.user_text.clone();
                    self.emit_transcript(Role::User, id, &current, &mut actions);
                }
                if in_tx.get("finished").and_then(Value::as_bool) == Some(true) {
                    self.finish_user_turn();
                }
            }

            if let Some(parts) = sc
                .get("modelTurn")
                .and_then(|m| m.get("parts"))
                .and_then(Value::as_array)
            {
                for part in parts {
                    let Some(data) = part
                        .get("inlineData")
                        .and_then(|d| d.get("data"))
                        .and_then(Value::as_str)
                        .filter(|s| !s.is_empty())
                    else {
                        continue;
                    };
                    let audio24 = decode_audio(data)?;
                    if !audio24.len().is_multiple_of(2) {
                        return Err(BridgeError::Value("Invalid Gemini audio frame"));
                    }
                    let mut buf = std::mem::take(&mut self.pcm24_rem);
                    buf.extend_from_slice(&audio24);
                    let usable = (buf.len() / 6) * 6;
                    self.pcm24_rem = buf[usable..].to_vec();
                    let audio8 = if usable > 0 {
                        downsample_24k_to_8k(&buf[..usable])?
                    } else {
                        Vec::new()
                    };
                    if self.playback.len() + audio8.len() > PLAYBACK_LIMIT {
                        return Err(BridgeError::Value("Invalid or excessive Gemini audio"));
                    }
                    if !audio8.is_empty() {
                        self.playback.extend(audio8);
                    }
                    self.finish_user_turn();
                    self.speaking = true;
                }
            }

            if let Some(out_tx) = sc.get("outputTranscription").and_then(Value::as_object) {
                if let Some(chunk) = out_tx.get("text").and_then(Value::as_str).filter(|s| !s.is_empty()) {
                    self.finish_user_turn();
                    self.assistant_text.push_str(chunk);
                    let id = format!("assistant-{}", self.assistant_turn);
                    let current = self.assistant_text.clone();
                    self.emit_transcript(Role::Assistant, id, &current, &mut actions);
                }
                if out_tx.get("finished").and_then(Value::as_bool) == Some(true) {
                    self.finish_assistant_turn();
                }
            }

            if sc.get("turnComplete").and_then(Value::as_bool) == Some(true) {
                self.speaking = false;
                self.finish_assistant_turn();
            }
        }

        if let Some(cancel_ids) = event
            .get("toolCallCancellation")
            .and_then(|c| c.get("ids"))
            .and_then(Value::as_array)
        {
            for cid in cancel_ids {
                if let Some(s) = cid.as_str().filter(|s| !s.is_empty()) {
                    self.seen_tools.insert(s.to_string());
                }
            }
        }

        if let Some(calls) = event
            .get("toolCall")
            .and_then(|c| c.get("functionCalls"))
            .and_then(Value::as_array)
        {
            for fc in calls {
                let Some(obj) = fc.as_object() else {
                    continue;
                };
                let Some(call_id) = obj
                    .get("id")
                    .and_then(Value::as_str)
                    .filter(|id| !id.is_empty() && id.chars().count() <= CALL_ID_CHARS)
                else {
                    continue;
                };
                if self.seen_tools.contains(call_id) {
                    continue;
                }
                if self.seen_tools.len() >= TOOL_LIMIT {
                    return Err(BridgeError::Value("Tool limit"));
                }
                self.seen_tools.insert(call_id.to_string());
                let name = obj
                    .get("name")
                    .cloned()
                    .unwrap_or_else(|| Value::String(String::new()));
                let args: Map<String, Value> = match obj.get("args") {
                    None | Some(Value::Null) => Map::new(),
                    Some(Value::Object(m)) => m.clone(),
                    Some(Value::String(text)) => match serde_json::from_str::<Value>(text)
                        .map_err(|_| BridgeError::Json)?
                    {
                        Value::Object(m) => m,
                        _ => return Err(BridgeError::Value("Invalid tool arguments")),
                    },
                    Some(_) => return Err(BridgeError::Value("Invalid tool arguments")),
                };
                if name.as_str() == Some("end_call") {
                    self.ending = true;
                    self.speaking = false;
                } else {
                    actions.push(Action::Tool {
                        call_id: call_id.to_string(),
                        name,
                        args,
                    });
                }
            }
        }

        Ok(actions)
    }

    pub fn output_tick(&mut self, now: f64) -> OutputStep {
        if !self.playback.is_empty() {
            let take = self.playback.len().min(FRAME_BYTES);
            let mut frame: Vec<u8> = self.playback.drain(..take).collect();
            frame.resize(FRAME_BYTES, 0);
            self.idle_since = None;
            return OutputStep::Frame(frame);
        }
        if self.ending && !self.speaking {
            let since = match self.idle_since {
                Some(t) if t != 0.0 => t,
                _ => now,
            };
            self.idle_since = Some(since);
            if now - since >= LINGER_SECONDS {
                return OutputStep::Finished;
            }
        }
        OutputStep::Wait
    }
}
