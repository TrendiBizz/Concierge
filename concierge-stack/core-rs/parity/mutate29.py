"""Mutation check for batch 29: break each rule once and require the parity tests to fail."""
import pathlib, subprocess, sys
src = pathlib.Path("src/media_bridge.rs")
original = src.read_text()
M = [
 ("barge-in keeps playback", "self.playback.clear();\n                self.ending = false;", "self.ending = false;"),
 ("barge-in keeps ending", "self.playback.clear();\n                self.ending = false;", "self.playback.clear();"),
 ("cancel when silent", "if self.speaking {", "if true {"),
 ("response.create on every session.updated", "if !self.ready {", "if true {"),
 ("ready never set", "self.ready = true;", ""),
 ("speaking never set", '"response.created" => self.speaking = true,', '"response.created" => {}'),
 ("speaking never cleared", "self.speaking = false;\n", "\n"),
 ("duplicate transcript passes", "== Some(text) {", '== Some("\\u{0}") {'),
 ("transcript not remembered", "self.seen_transcripts.insert(key, text.to_string());", ""),
 ("transcript cut at 10001", "TRANSCRIPT_CHARS: usize = 10000", "TRANSCRIPT_CHARS: usize = 10001"),
 ("transcript cut by bytes", "text: text.chars().take(TRANSCRIPT_CHARS).collect(),", "text: String::from_utf8_lossy(&text.as_bytes()[..text.len().min(TRANSCRIPT_CHARS)]).into_owned(),"),
 ("roles swapped", 'kind.starts_with("conversation")', 'kind.starts_with("response")'),
 ("falsy item_id not skipped", "Some(item) if truthy(item) => Some(item),", "Some(item) => Some(item),"),
 ("empty text passes", ".filter(|t| !t.is_empty())", ""),
 ("non-text id accepted as none", 'return Err(BridgeError::Unsupported("transcript identifier is not text"))', "None"),
 ("call id 201 chars", "CALL_ID_CHARS: usize = 200", "CALL_ID_CHARS: usize = 201"),
 ("call id length in bytes", "id.chars().count() <= CALL_ID_CHARS", "id.len() <= CALL_ID_CHARS"),
 ("empty call id accepted", "!id.is_empty() && id.chars()", "id.chars()"),
 ("tool limit 41", "TOOL_LIMIT: usize = 40", "TOOL_LIMIT: usize = 41"),
 ("repeated tool runs again", "self.seen_tools.insert(call_id.to_string());", ""),
 ("missing arguments refused", "None => Value::Object(Map::new()),", "None => return Err(BridgeError::Type),"),
 ("non-object arguments accepted", 'let Value::Object(args) = args else {\n            return Err(BridgeError::Value("Invalid tool arguments"));\n        };', "let args = args.as_object().cloned().unwrap_or_default();"),
 ("end_call does not end", "self.ending = true;", ""),
 ("end_call runs as a tool", 'name.as_str() == Some("end_call")', 'name.as_str() == Some("end_call!")'),
 ("response.create after end_call", "if any && !self.ending {", "if any {"),
 ("response.create with nothing pending", "if any && !self.ending {", "if !self.ending {"),
 ("pending not cleared", "std::mem::take(&mut self.pending)", "self.pending.clone()"),
 ("playback limit +2", "PLAYBACK_LIMIT: usize = 16000 * 30", "PLAYBACK_LIMIT: usize = 16000 * 30 + 2"),
 ("playback limit exclusive", "self.playback.len() + audio.len() > PLAYBACK_LIMIT", "self.playback.len() + audio.len() >= PLAYBACK_LIMIT"),
 ("odd audio accepted", "!audio.len().is_multiple_of(2)\n                    || ", ""),
 ("missing delta ignored", 'event.get("delta").ok_or(BridgeError::Key)?', 'event.get("delta").ok_or(BridgeError::Type)?'),
 ("error event ignored", '"error" => return Err(BridgeError::Runtime("Grok rejected telephone session")),', '"error" => {}'),
 ("trailing bits refused", "with_decode_allow_trailing_bits(true)", "with_decode_allow_trailing_bits(false)"),
 ("padding optional", "DecodePaddingMode::RequireCanonical", "DecodePaddingMode::Indifferent"),
 ("frame not padded", "frame.resize(FRAME_BYTES, 0);", ""),
 ("frame 322 bytes", "FRAME_BYTES: usize = 320", "FRAME_BYTES: usize = 322"),
 ("linger not reset by audio", "self.idle_since = None;", ""),
 ("zero clock counts as set", "Some(t) if t != 0.0 => t,", "Some(t) => t,"),
 ("linger exclusive", "now - since >= LINGER_SECONDS", "now - since > LINGER_SECONDS"),
 ("linger 0.42", "LINGER_SECONDS: f64 = 0.4", "LINGER_SECONDS: f64 = 0.42"),
 ("release while speaking", "if self.ending && !self.speaking {", "if self.ending {"),
 ("release without end_call", "if self.ending && !self.speaking {", "if !self.speaking {"),
 ("linger restarts each tick", "self.idle_since = Some(since);", ""),
 ("negative sleep", "if rest > 0.0 {", "if true {"),
 ("empty audio packet accepted", "body.is_empty() || ", ""),
 ("odd audio packet accepted", "body.is_empty() || !body.len().is_multiple_of(2)", "body.is_empty()"),
 ("any keypad length", "3 if body.len() == 1 => Ok(Inbound::Ignore),", "3 => Ok(Inbound::Ignore),"),
 ("hangup needs empty body", "0 => Ok(Inbound::Hangup),", "0 if body.is_empty() => Ok(Inbound::Hangup),"),
 ("oversize checked after body", "if self.buffer.len() < 3 {", "if self.buffer.len() < 3 + 8194 {"),
 ("packet body off by one", "self.buffer[3..3 + length].to_vec()", "self.buffer[2..2 + length].to_vec()"),
 ("tool result for wrong call accepted", "if self.awaiting_tool.as_deref() != Some(call_id) {", "if false {"),
]
survivors, missing = [], []
try:
    for name, old, new in M:
        if original.count(old) != 1:
            missing.append((name, original.count(old))); continue
        src.write_text(original.replace(old, new))
        r = subprocess.run(["cargo", "test", "--locked", "--test", "parity29"], capture_output=True, text=True)
        killed = r.returncode != 0
        print(("killed  " if killed else "SURVIVED"), name, flush=True)
        if not killed: survivors.append(name)
finally:
    src.write_text(original)
print("mutants", len(M), "survivors", survivors, "pattern-missing", missing)
