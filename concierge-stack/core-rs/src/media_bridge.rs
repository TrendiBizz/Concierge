//! The telephone media bridge as a pure state machine (port of `asterisk_bridge.MediaBridge`: the Grok event handler, the
//! playback pacer and the AudioSocket input rules). No sockets, no clock and no database live here: the caller feeds in
//! websocket text, AudioSocket bytes and the time, and carries out the returned actions. That is what makes every rule
//! testable against the live Python (`parity/gen_vectors29.py` -> `tests/parity29.rs`).
//!
//! Deliberately kept Python behaviours:
//! * `idle_since` is cleared only by playing audio. A withdrawn `end_call` (barge-in) does not restart the 0.4 s linger.
//! * A linger that begins at clock value `0.0` restarts on the next tick (`idle_since or started` treats 0.0 as unset).
//! * A tool identifier is remembered before its arguments are checked.
//!
//! Where this port refuses instead of guessing (it can only end a call Python would have continued, never the reverse):
//! * JSON that only Python accepts: `NaN`/`Infinity` literals, numbers beyond a double, lone surrogate escapes.
//! * A transcript whose identifier is a number, `true`, a list or an object (Grok sends strings).
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
/// Seconds to wait for Grok to accept the session before any caller audio is read.
pub const READY_SECONDS: u64 = 15;
/// Seconds of silence, after `end_call` and the last audio, before the line is released.
pub const LINGER_SECONDS: f64 = 0.4;
/// Thirty seconds of queued speech; more than this from Grok ends the call.
pub const PLAYBACK_LIMIT: usize = 16000 * 30;
/// Tool calls allowed in one call.
pub const TOOL_LIMIT: usize = 40;
const TRANSCRIPT_CHARS: usize = 10000;
const CALL_ID_CHARS: usize = 200;

/// What Python raised, by kind. `class()` gives the name the parity vectors use.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BridgeError {
    /// `json.JSONDecodeError`.
    Json,
    /// The message was valid JSON but not an object (`AttributeError` on `.get`).
    NotObject,
    /// A required field was missing (`KeyError`).
    Key,
    /// A field had the wrong type (`TypeError`).
    Type,
    /// `base64.b64decode(..., validate=True)` refused the audio.
    Base64,
    /// `ValueError` with this message.
    Value(&'static str),
    /// `RuntimeError` with this message.
    Runtime(&'static str),
    /// The stream ended inside or between packets (`asyncio.IncompleteReadError`): the caller hung up without a hangup frame.
    IncompleteRead,
    /// Python would continue; this port refuses rather than guess.
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

/// Something the caller must do, in the order returned.
#[derive(Debug, Clone, PartialEq)]
pub enum Action {
    /// Send this JSON to Grok.
    Send(Value),
    /// Store this turn. With an `item_id`, a later transcript for the same id and role REPLACES the stored text.
    Transcript {
        role: Role,
        text: String,
        item_id: Option<String>,
    },
    /// Run this tool, then call [`Bridge::tool_result`] with its output BEFORE feeding the next Grok message.
    Tool {
        call_id: String,
        name: Value,
        args: Map<String, Value>,
    },
}

/// One 20 ms playback tick.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OutputStep {
    /// Write this (always `FRAME_BYTES` long) to the caller as an audio packet, and add it to the recording.
    Frame(Vec<u8>),
    /// Nothing to play.
    Wait,
    /// The call was ended by the model and its goodbye has been played: release the line.
    Finished,
}

/// What one AudioSocket packet from the caller means.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Inbound {
    /// The caller hung up.
    Hangup,
    /// Forward the body to Grok and add it to the recording.
    Audio,
    /// A keypad digit: nothing is forwarded and no silence is substituted.
    Ignore,
}

/// Python truthiness of a JSON value (`x or y`).
fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().is_some_and(|f| f != 0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

/// `base64.b64decode(text, validate=True)`: standard alphabet, padding required, nothing after it. Like Python, unused
/// bits in the last character are not checked.
pub fn decode_audio(text: &str) -> Result<Vec<u8>, BridgeError> {
    const ENGINE: GeneralPurpose = GeneralPurpose::new(
        &alphabet::STANDARD,
        GeneralPurposeConfig::new()
            .with_decode_allow_trailing_bits(true)
            .with_decode_padding_mode(DecodePaddingMode::RequireCanonical),
    );
    ENGINE.decode(text).map_err(|_| BridgeError::Base64)
}

/// `json.dumps(result, default=str)` for a tool result that is already plain JSON. A result holding a float is written
/// the way serde writes it (Python's shortest float text can differ), which the model reads the same.
pub fn tool_output(result: &Value) -> String {
    pyjson::dumps(result).unwrap_or_else(|| result.to_string())
}

/// Whether a caller packet is audio, a hangup or ignorable; anything else ends the call.
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

/// The message that carries caller audio (or substituted silence) to Grok.
pub fn append_event(body: &[u8]) -> Value {
    json!({"type": "input_audio_buffer.append", "audio": STANDARD.encode(body)})
}

/// The silence sent to Grok when the caller's side delivers no packet for 20 ms, so that its voice detection can still
/// finish the caller's turn.
pub fn silence() -> Vec<u8> {
    vec![0; FRAME_BYTES]
}

/// How long the playback loop sleeps after a tick that began at `started` and finished its write at `now`.
pub fn pace(started: f64, now: f64) -> f64 {
    let rest = FRAME_SECONDS - (now - started);
    if rest > 0.0 {
        rest
    } else {
        0.0
    }
}

/// Reassembles AudioSocket packets from however the bytes arrive. Nothing is lost when a read is interrupted half-way
/// through a packet, which is what Python protects with a shielded read task.
#[derive(Default)]
pub struct Deframer {
    buffer: Vec<u8>,
}

impl Deframer {
    pub fn push(&mut self, bytes: &[u8]) {
        self.buffer.extend_from_slice(bytes);
    }

    /// The next complete packet, `Ok(None)` when more bytes are needed. An oversized length is refused as soon as the
    /// three header bytes are in, before any of the body arrives.
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

    /// The stream closed. Python's `readexactly` raises at end of stream whether or not a packet was half read.
    pub fn end_of_stream(&self) -> BridgeError {
        BridgeError::IncompleteRead
    }
}

/// The state the three loops of one call share.
#[derive(Default)]
pub struct Bridge {
    /// Speech from Grok not yet played to the caller.
    pub playback: VecDeque<u8>,
    /// Grok has accepted the session; caller audio may flow.
    pub ready: bool,
    /// The model asked to end the call.
    pub ending: bool,
    /// Grok is producing a response.
    pub speaking: bool,
    /// When the line last went quiet while ending.
    pub idle_since: Option<f64>,
    pending: Vec<(String, String)>,
    awaiting_tool: Option<String>,
    seen_transcripts: HashMap<(String, Role), String>,
    seen_tools: HashSet<String>,
}

impl Bridge {
    pub fn new() -> Self {
        Self::default()
    }

    /// Tool results waiting for Grok's `response.done`, as (call id, output text).
    pub fn pending(&self) -> &[(String, String)] {
        &self.pending
    }

    /// The first message of every call.
    pub fn start(&self, session: &Value) -> Action {
        Action::Send(json!({"type": "session.update", "session": session}))
    }

    /// Hand in the output of the tool most recently requested by [`Action::Tool`], as the exact text Grok should receive
    /// (see [`tool_output`]). Returns `false`, changing nothing, if that call is not the one being waited for.
    pub fn tool_result(&mut self, call_id: &str, output: String) -> bool {
        if self.awaiting_tool.as_deref() != Some(call_id) {
            return false;
        }
        self.awaiting_tool = None;
        self.pending.push((call_id.to_string(), output));
        true
    }

    /// One websocket message from Grok. An `Err` ends the call; no action has been taken for that message.
    pub fn on_message(&mut self, text: &str) -> Result<Vec<Action>, BridgeError> {
        if self.awaiting_tool.is_some() {
            return Err(BridgeError::Unsupported(
                "tool result not supplied before the next message",
            ));
        }
        let parsed: Value = serde_json::from_str(text).map_err(|_| BridgeError::Json)?;
        let event = parsed.as_object().ok_or(BridgeError::NotObject)?;
        let mut actions = Vec::new();
        let Some(kind) = event.get("type").and_then(Value::as_str) else {
            return Ok(actions);
        };
        match kind {
            "session.updated" => {
                if !self.ready {
                    self.ready = true;
                    actions.push(Action::Send(json!({"type": "response.create"})));
                }
            }
            "error" => return Err(BridgeError::Runtime("Grok rejected telephone session")),
            "response.created" => self.speaking = true,
            "response.output_audio.delta" | "response.audio.delta" => {
                let delta = event.get("delta").ok_or(BridgeError::Key)?;
                let audio = decode_audio(delta.as_str().ok_or(BridgeError::Type)?)?;
                if !audio.len().is_multiple_of(2)
                    || self.playback.len() + audio.len() > PLAYBACK_LIMIT
                {
                    return Err(BridgeError::Value("Invalid or excessive Grok audio"));
                }
                self.playback.extend(audio);
            }
            "input_audio_buffer.speech_started" => {
                self.playback.clear();
                self.ending = false;
                if self.speaking {
                    actions.push(Action::Send(json!({"type": "response.cancel"})));
                }
            }
            "conversation.item.input_audio_transcription.completed"
            | "response.output_audio_transcript.done"
            | "response.audio_transcript.done" => {
                let role = if kind.starts_with("conversation") {
                    Role::User
                } else {
                    Role::Assistant
                };
                self.transcript(event, role, &mut actions)?;
            }
            "response.function_call_arguments.done" => self.tool_call(event, &mut actions)?,
            "response.done" => {
                self.speaking = false;
                let pending = std::mem::take(&mut self.pending);
                let any = !pending.is_empty();
                for (call_id, output) in pending {
                    actions.push(Action::Send(
                        json!({"type": "conversation.item.create", "item": {
                        "type": "function_call_output", "call_id": call_id, "output": output}}),
                    ));
                }
                if any && !self.ending {
                    actions.push(Action::Send(json!({"type": "response.create"})));
                }
            }
            _ => {}
        }
        Ok(actions)
    }

    fn transcript(
        &mut self,
        event: &Map<String, Value>,
        role: Role,
        actions: &mut Vec<Action>,
    ) -> Result<(), BridgeError> {
        // `event.get('item_id') or event.get('response_id')`
        let identity = match event.get("item_id") {
            Some(item) if truthy(item) => Some(item),
            _ => event.get("response_id"),
        };
        let Some(text) = event
            .get("transcript")
            .and_then(Value::as_str)
            .filter(|t| !t.is_empty())
        else {
            return Ok(());
        };
        let item_id = match identity {
            Some(Value::String(s)) if !s.is_empty() => Some(s.clone()),
            Some(other) if truthy(other) => {
                return Err(BridgeError::Unsupported(
                    "transcript identifier is not text",
                ))
            }
            _ => None,
        };
        if let Some(id) = &item_id {
            // Grok can send successive cumulative transcripts for one item: the same text again is dropped, a new text
            // is passed on so the stored turn can be replaced.
            let key = (id.clone(), role);
            if self.seen_transcripts.get(&key).map(String::as_str) == Some(text) {
                return Ok(());
            }
            self.seen_transcripts.insert(key, text.to_string());
        }
        actions.push(Action::Transcript {
            role,
            text: text.chars().take(TRANSCRIPT_CHARS).collect(),
            item_id,
        });
        Ok(())
    }

    fn tool_call(
        &mut self,
        event: &Map<String, Value>,
        actions: &mut Vec<Action>,
    ) -> Result<(), BridgeError> {
        let Some(call_id) = event
            .get("call_id")
            .and_then(Value::as_str)
            .filter(|id| !id.is_empty() && id.chars().count() <= CALL_ID_CHARS)
        else {
            return Ok(());
        };
        if self.seen_tools.contains(call_id) {
            return Ok(());
        }
        if self.seen_tools.len() >= TOOL_LIMIT {
            return Err(BridgeError::Value("Tool limit"));
        }
        self.seen_tools.insert(call_id.to_string());
        // `json.loads(event.get('arguments', '{}'))`
        let args: Value = match event.get("arguments") {
            None => Value::Object(Map::new()),
            Some(Value::String(text)) => {
                serde_json::from_str(text).map_err(|_| BridgeError::Json)?
            }
            Some(_) => return Err(BridgeError::Type),
        };
        let Value::Object(args) = args else {
            return Err(BridgeError::Value("Invalid tool arguments"));
        };
        let name = event
            .get("name")
            .cloned()
            .unwrap_or_else(|| Value::String(String::new()));
        if name.as_str() == Some("end_call") {
            self.ending = true;
            self.pending.push((
                call_id.to_string(),
                tool_output(&json!({"ok": true, "ending": true})),
            ));
        } else {
            self.awaiting_tool = Some(call_id.to_string());
            actions.push(Action::Tool {
                call_id: call_id.to_string(),
                name,
                args,
            });
        }
        Ok(())
    }

    /// One playback tick at clock time `now` (seconds, any monotonic origin). Call every 20 ms; see [`pace`].
    pub fn output_tick(&mut self, now: f64) -> OutputStep {
        if !self.playback.is_empty() {
            let take = self.playback.len().min(FRAME_BYTES);
            let mut frame: Vec<u8> = self.playback.drain(..take).collect();
            frame.resize(FRAME_BYTES, 0);
            self.idle_since = None;
            return OutputStep::Frame(frame);
        }
        if self.ending && !self.speaking {
            // `idle_since = idle_since or started`: 0.0 counts as unset, exactly as in Python.
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
