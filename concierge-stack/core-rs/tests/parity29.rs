//! Batch 29: the telephone media bridge (`asterisk_bridge.MediaBridge`). Every expected value was produced by the live
//! Python class under scripted sockets and a virtual clock (`parity/gen_vectors29.py` -> `parity/vectors29.json`).
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use concierge_core::media_bridge::{
    self as mb, Action, Bridge, BridgeError, Deframer, Inbound, OutputStep,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors29.json")).unwrap()
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}

fn double(bits: &Value) -> f64 {
    f64::from_bits(u64::from_str_radix(bits.as_str().unwrap(), 16).unwrap())
}

/// A vector message is raw websocket text, or `{"zeros": n, "type": kind}` standing for n zero bytes of audio.
fn expand(message: &Value) -> String {
    match message.as_str() {
        Some(text) => text.to_string(),
        None => json!({"type": message["type"], "delta": STANDARD.encode(vec![0u8; message["zeros"].as_u64().unwrap() as usize])})
            .to_string(),
    }
}

fn state(bridge: &Bridge) -> Value {
    let playback: Vec<u8> = bridge.playback.iter().copied().collect();
    json!({
        "playback_len": playback.len(),
        "playback_sha256": hex(&Sha256::digest(&playback)),
        "ready": bridge.ready,
        "ending": bridge.ending,
        "speaking": bridge.speaking,
        "pending": bridge.pending().iter().map(|(id, out)| json!([id, out])).collect::<Vec<_>>(),
    })
}

/// Carries out the actions the way the caller must, answering each tool with the output the live Python tool produced.
fn log(bridge: &mut Bridge, actions: Vec<Action>, expected: &Value) -> Value {
    let mut entries = Vec::new();
    for action in actions {
        match action {
            Action::Send(value) => entries.push(json!({"send": value})),
            Action::Transcript {
                role,
                text,
                item_id,
            } => entries.push(json!({"transcript": [role.as_str(), text, item_id]})),
            Action::Tool {
                call_id,
                name,
                args,
            } => {
                let output = expected
                    .as_array()
                    .and_then(|log| log.get(entries.len()))
                    .and_then(|entry| entry["output"].as_str())
                    .expect("Python ran no tool at this point")
                    .to_string();
                assert!(
                    !bridge.tool_result("some-other-call", output.clone()),
                    "a result for the wrong call was accepted"
                );
                assert!(bridge.tool_result(&call_id, output.clone()));
                entries.push(json!({"tool": [name, args], "output": output}));
            }
        }
    }
    Value::Array(entries)
}

#[test]
fn grok_events_match_python() {
    let v = vectors();
    let cases = v["grok"].as_array().unwrap();
    let (mut messages, mut actions, mut errors, mut declined) = (0, 0, 0, 0);
    for (n, case) in cases.iter().enumerate() {
        let steps = case["steps"].as_array().unwrap();
        let mut bridge = Bridge::new();
        let opening = vec![bridge.start(&case["session"])];
        let first = log(&mut bridge, opening, &steps[0]["log"]);
        assert_eq!(first, steps[0]["log"], "case {n}: session.update");
        assert_eq!(state(&bridge), steps[0]["state"], "case {n}: first state");
        let refused_at = case.get("declined").and_then(Value::as_u64);
        let mut end = "closed".to_string();
        for (i, message) in case["messages"].as_array().unwrap().iter().enumerate() {
            let before = state(&bridge);
            match bridge.on_message(&expand(message)) {
                Ok(done) => {
                    assert_ne!(
                        refused_at,
                        Some(i as u64),
                        "case {n}: message {i} must be refused"
                    );
                    let step = steps.get(i + 1).unwrap_or_else(|| {
                        panic!(
                            "case {n}: Python stopped at message {i} with {}",
                            case["end"]
                        )
                    });
                    actions += done.len();
                    let got = log(&mut bridge, done, &step["log"]);
                    assert_eq!(got, step["log"], "case {n} message {i}: actions");
                    assert_eq!(state(&bridge), step["state"], "case {n} message {i}: state");
                    messages += 1;
                }
                Err(error) => {
                    assert_eq!(
                        state(&bridge),
                        before,
                        "case {n} message {i}: state changed by a refused message"
                    );
                    if refused_at == Some(i as u64) {
                        assert!(
                            matches!(error, BridgeError::Json | BridgeError::Unsupported(_)),
                            "case {n}: {error}"
                        );
                        declined += 1;
                        end = String::new();
                    } else {
                        assert_eq!(steps.len(), i + 1, "case {n}: Python accepted message {i}");
                        assert_eq!(
                            case["partial"],
                            json!([]),
                            "case {n}: Python acted before raising"
                        );
                        end = error.class();
                        errors += 1;
                    }
                    break;
                }
            }
        }
        if refused_at.is_none() {
            assert_eq!(end, case["end"].as_str().unwrap(), "case {n}: how it ended");
        }
    }
    assert!(
        cases.len() >= 200 && messages >= 4000 && actions >= 1500,
        "{messages} messages, {actions} actions"
    );
    assert!(
        errors >= 35 && declined == 14,
        "{errors} errors, {declined} declined"
    );
}

#[test]
fn playback_pacing_matches_python() {
    let v = vectors();
    let cases = v["output"].as_array().unwrap();
    let (mut ticks, mut frames, mut finished) = (0, 0, 0);
    for (n, case) in cases.iter().enumerate() {
        let mut bridge = Bridge::new();
        let apply = |bridge: &mut Bridge, batch: &Value| {
            for op in batch.as_array().unwrap() {
                match op[0].as_str().unwrap() {
                    "extend" => bridge.playback.extend(unhex(op[1].as_str().unwrap())),
                    "clear" => bridge.playback.clear(),
                    "ending" => bridge.ending = op[1].as_bool().unwrap(),
                    "speaking" => bridge.speaking = op[1].as_bool().unwrap(),
                    "delay" => {}
                    other => panic!("unknown op {other}"),
                }
            }
        };
        apply(&mut bridge, &case["init"]);
        let all = case["ticks"].as_array().unwrap();
        let ops = case["ops"].as_array().unwrap();
        for (i, tick) in all.iter().enumerate() {
            let now = double(&tick["now"]);
            let step = bridge.output_tick(now);
            ticks += 1;
            let last = i + 1 == all.len();
            match (&step, tick["frame"].as_str()) {
                (OutputStep::Frame(frame), Some(want)) => {
                    assert_eq!(hex(frame), want, "case {n} tick {i}");
                    assert_eq!(frame.len(), mb::FRAME_BYTES);
                    frames += 1;
                }
                (OutputStep::Finished, None) => {
                    assert!(
                        last && case["finished"] == json!(true),
                        "case {n} tick {i}: finished early"
                    );
                    finished += 1;
                }
                (OutputStep::Wait, None) => assert!(
                    !(last && case["finished"] == json!(true)),
                    "case {n} tick {i}: Python released the line here"
                ),
                (got, want) => panic!("case {n} tick {i}: {got:?} but Python wrote {want:?}"),
            }
            if !tick["slept"].is_null() {
                let slept = mb::pace(now, double(&tick["after_write"]));
                assert_eq!(
                    slept.to_bits(),
                    double(&tick["slept"]).to_bits(),
                    "case {n} tick {i}: sleep"
                );
            }
            if let Some(batch) = ops.get(i) {
                if !last {
                    apply(&mut bridge, batch);
                }
            }
        }
        assert_eq!(
            bridge.playback.len() as u64,
            case["left"].as_u64().unwrap(),
            "case {n}: audio left"
        );
    }
    assert!(
        cases.len() >= 75 && ticks >= 3000 && frames >= 300 && finished >= 30,
        "{ticks} ticks, {frames} frames, {finished} finished"
    );
}

/// Runs one caller byte stream through the deframer and the packet rules, delivered in chunks of the given sizes.
fn run_input(stream: &[u8], chunk: impl Fn(usize) -> usize) -> (Vec<String>, String) {
    let mut deframer = Deframer::default();
    let mut sent = Vec::new();
    let mut offset = 0;
    let mut round = 0;
    loop {
        loop {
            match deframer.next_packet() {
                Ok(Some((kind, body))) => match mb::classify(kind, &body) {
                    Ok(Inbound::Hangup) => return (sent, "hangup".into()),
                    Ok(Inbound::Audio) => {
                        let event = mb::append_event(&body);
                        assert_eq!(event["type"], "input_audio_buffer.append");
                        assert_eq!(event.as_object().unwrap().len(), 2);
                        sent.push(hex(&STANDARD
                            .decode(event["audio"].as_str().unwrap())
                            .unwrap()));
                    }
                    Ok(Inbound::Ignore) => {}
                    Err(error) => return (sent, error.class()),
                },
                Ok(None) => break,
                Err(error) => return (sent, error.class()),
            }
        }
        if offset == stream.len() {
            return (sent, deframer.end_of_stream().class());
        }
        let take = chunk(round).clamp(1, stream.len() - offset);
        deframer.push(&stream[offset..offset + take]);
        offset += take;
        round += 1;
    }
}

#[test]
fn caller_packets_match_python_however_the_bytes_arrive() {
    let v = vectors();
    let cases = v["input"].as_array().unwrap();
    let (mut audio, mut refused) = (0, 0);
    for (n, case) in cases.iter().enumerate() {
        let stream = unhex(case["stream"].as_str().unwrap());
        let want: Vec<String> = case["sent"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s.as_str().unwrap().to_string())
            .collect();
        let end = case["end"].as_str().unwrap();
        // whole, byte by byte, and in uneven pieces that split headers and bodies differently each time
        for (name, sizes) in [
            ("whole", vec![usize::MAX]),
            ("bytes", vec![1]),
            ("pairs", vec![2]),
            ("uneven", vec![1, 5, 2, 319, 3, 7, 4000, 1, 1, 640]),
            ("primes", vec![3, 317, 11, 2, 163, 8191, 5]),
        ] {
            let (sent, got) = run_input(&stream, |round| sizes[round % sizes.len()]);
            assert_eq!(got, end, "case {n} ({name}): how it ended");
            assert_eq!(sent, want, "case {n} ({name}): audio forwarded");
        }
        audio += want.len();
        refused += usize::from(end.starts_with("value:"));
    }
    assert!(
        cases.len() >= 85 && audio >= 100 && refused >= 20,
        "{audio} frames, {refused} refused"
    );
    assert_eq!(mb::silence(), vec![0u8; 320]);
}

#[test]
fn audio_decoding_matches_python_strict_base64() {
    let v = vectors();
    let cases = v["b64"].as_array().unwrap();
    let (mut accepted, mut refused) = (0, 0);
    for case in cases {
        let text = case["text"].as_str().unwrap();
        match (mb::decode_audio(text), case["hex"].as_str()) {
            (Ok(bytes), Some(want)) => {
                assert_eq!(hex(&bytes), want, "{text:?}");
                accepted += 1;
            }
            (Err(BridgeError::Base64), None) => refused += 1,
            (got, want) => panic!("{text:?}: {got:?} but Python gave {want:?}"),
        }
    }
    assert!(
        accepted >= 80 && refused >= 300,
        "{accepted} accepted, {refused} refused"
    );
}
