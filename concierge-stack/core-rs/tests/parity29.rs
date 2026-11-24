//! Batch 29: Google Gemini 3.8 Live telephone media bridge (`media_bridge::Bridge`) unit and protocol tests.
use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use concierge_core::media_bridge::{
    self as mb, Action, Bridge, BridgeError, Deframer, Inbound, OutputStep, Role,
};
use serde_json::json;

#[test]
fn gemini_resampling_8k_to_16k_and_24k_to_8k() {
    assert_eq!(mb::upsample_8k_to_16k(&vec![0u8; 320]).unwrap().len(), 640);
    assert_eq!(mb::downsample_24k_to_8k(&vec![0u8; 960]).unwrap().len(), 320);

    let ramp: Vec<u8> = [0i16, 100, -100]
        .iter()
        .flat_map(|s| s.to_le_bytes())
        .collect();
    let up = mb::upsample_8k_to_16k(&ramp).unwrap();
    let up_samples: Vec<i16> = up
        .chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect();
    assert_eq!(up_samples, vec![0, 50, 100, 0, -100, -100]);

    let pcm24: Vec<u8> = [300i16, 600, 900, -300, -600, -900]
        .iter()
        .flat_map(|s| s.to_le_bytes())
        .collect();
    let down = mb::downsample_24k_to_8k(&pcm24).unwrap();
    let down_samples: Vec<i16> = down
        .chunks_exact(2)
        .map(|c| i16::from_le_bytes([c[0], c[1]]))
        .collect();
    assert_eq!(down_samples, vec![600, -600]);

    assert_eq!(
        mb::upsample_8k_to_16k(&[0, 1, 2]),
        Err(BridgeError::Value("Invalid PCM16 frame"))
    );
    assert_eq!(
        mb::downsample_24k_to_8k(&[0, 1, 2]),
        Err(BridgeError::Value("Invalid PCM16 frame"))
    );
}

#[test]
fn gemini_live_setup_audio_transcripts_barge_in_and_tools() {
    let mut bridge = Bridge::new();
    let session = json!({
        "model": "models/gemini-3.8-live",
        "gemini_voice": "Aoede",
        "instructions": "You are a receptionist.",
        "tools": [
            {
                "type": "function",
                "name": "search_knowledge",
                "description": "Search business facts",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "additionalProperties": false
                }
            },
            {
                "type": "function",
                "name": "end_call",
                "description": "End after goodbye",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": false}
            }
        ]
    });
    let Action::Send(setup_msg) = bridge.start(&session) else {
        panic!("expected Send");
    };
    let setup = &setup_msg["setup"];
    assert_eq!(setup["model"], "models/gemini-3.8-live");
    assert_eq!(
        setup["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"],
        "Aoede"
    );
    assert!(setup["generationConfig"].get("thinkingConfig").is_none());
    let decls = setup["tools"][0]["functionDeclarations"].as_array().unwrap();
    assert_eq!(decls.len(), 2);
    assert!(decls[0]["parameters"].get("additionalProperties").is_none());
    assert!(decls[1].get("parameters").is_none());

    // setupComplete triggers greeting
    let actions = bridge.on_message(&json!({"setupComplete": {}}).to_string()).unwrap();
    assert!(bridge.ready);
    assert_eq!(actions.len(), 1);
    assert!(matches!(&actions[0], Action::Send(v) if v.get("clientContent").is_some()));

    // 24kHz Gemini audio -> 8kHz playback
    let audio24 = STANDARD.encode(vec![4u8; 960]);
    let actions = bridge
        .on_message(
            &json!({
                "serverContent": {
                    "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": audio24}}]},
                    "outputTranscription": {"text": "Hello caller", "finished": true}
                }
            })
            .to_string(),
        )
        .unwrap();
    assert!(bridge.speaking);
    assert_eq!(bridge.playback.len(), 320);
    assert!(actions.iter().any(|a| matches!(a, Action::Transcript { role: Role::Assistant, text, .. } if text == "Hello caller")));

    // Barge-in clears playback
    bridge
        .on_message(&json!({"serverContent": {"interrupted": true}}).to_string())
        .unwrap();
    assert!(bridge.playback.is_empty());
    assert!(!bridge.speaking);

    // Tool call
    let actions = bridge
        .on_message(
            &json!({
                "toolCall": {"functionCalls": [{"id": "t1", "name": "search_knowledge", "args": {"query": "hours"}}]}
            })
            .to_string(),
        )
        .unwrap();
    assert!(matches!(&actions[0], Action::Tool { call_id, .. } if call_id == "t1"));

    // end_call lingers 0.4s then finishes
    bridge
        .on_message(
            &json!({
                "toolCall": {"functionCalls": [{"id": "t2", "name": "end_call", "args": {}}]}
            })
            .to_string(),
        )
        .unwrap();
    assert!(bridge.ending);
    assert_eq!(bridge.output_tick(1.0), OutputStep::Wait);
    assert_eq!(bridge.output_tick(1.45), OutputStep::Finished);
}

#[test]
fn deframer_and_classify_rules() {
    assert_eq!(mb::classify(0, &[]), Ok(Inbound::Hangup));
    assert_eq!(mb::classify(0x10, &[0; 320]), Ok(Inbound::Audio));
    assert_eq!(mb::classify(3, &[b'1']), Ok(Inbound::Ignore));
    assert!(mb::classify(0x10, &[0, 1, 2]).is_err());

    let mut d = Deframer::default();
    d.push(&[0x10, 0, 2, 1, 2]);
    assert_eq!(d.next_packet().unwrap(), Some((0x10, vec![1, 2])));
    assert_eq!(d.next_packet().unwrap(), None);
}
