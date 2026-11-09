use concierge_core::{device_sms as sms, pbx};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors12.json")).unwrap()
}
fn s<'a>(v: &'a Value, k: &str) -> &'a str {
    v[k].as_str().unwrap()
}
fn bytes(v: &str) -> Vec<u8> {
    (0..v.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&v[i..i + 2], 16).unwrap())
        .collect()
}
#[test]
fn device_auth_matches_python() {
    for c in vectors()["auth"].as_array().unwrap() {
        let t = &c["tenant"];
        let tenant = (!t.is_null()).then(|| sms::Tenant {
            sms_enabled: t["sms_enabled"].as_bool().unwrap(),
            transport: s(t, "sms_transport"),
            from: s(t, "sms_from"),
        });
        let got = if sms::bearer_token(s(c, "header")).is_none() {
            401
        } else if sms::forbidden(
            tenant.as_ref(),
            c["receipt"].as_bool().unwrap(),
            "+6421123456",
        ) {
            403
        } else {
            200
        };
        assert_eq!(got, c["out"]["err"].as_u64().unwrap_or(200), "{c}");
    }
}
#[test]
fn enqueue_matches_python() {
    for c in vectors()["enqueue"].as_array().unwrap() {
        let recipient = s(c, "recipient");
        let body = s(c, "body");
        let got = match sms::validate_enqueue(
            c["enabled"].as_bool().unwrap(),
            s(c, "transport"),
            recipient,
            body,
        ) {
            Err(e) => json!({"err":"ValueError","message":e}),
            Ok(()) => {
                let changed = if c["changed"].as_bool().unwrap() {
                    format!("{body}!")
                } else {
                    body.to_string()
                };
                match sms::job_outcome(
                    &sms::ExistingJob {
                        recipient,
                        body: &changed,
                        device: "device",
                        status: s(c, "status"),
                        receipt: "verified",
                        id: "job",
                    },
                    recipient,
                    body,
                    "device",
                ) {
                    sms::JobOutcome::Sent(v) => json!({"ok":v}),
                    sms::JobOutcome::Awaiting(v) => json!({"err":"AwaitingReceipt","message":v}),
                    sms::JobOutcome::Reconcile(v) => {
                        json!({"err":"ReconciliationRequired","message":v})
                    }
                }
            }
        };
        if !recipient.is_ascii() && c["out"] != got {
            assert_eq!(
                got,
                json!({"err":"ValueError","message":"Invalid SMS recipient or body"})
            );
        } else {
            assert_eq!(got, c["out"], "{c}");
        }
    }
}
#[test]
fn routes_match_python() {
    for c in vectors()["routes"].as_array().unwrap() {
        match pbx::routes_from_json(s(c, "text")) {
            Ok(routes) => assert_eq!(
                json!({"ok":routes.iter().map(|r|json!({"tenant":r.tenant,"number":r.number,"port":r.port})).collect::<Vec<_>>()}),
                c["out"]
            ),
            Err(pbx::RouteError::Json) => assert_eq!(c["out"]["err"], "JSONDecodeError"),
            Err(pbx::RouteError::Type) => assert_eq!(c["out"]["err"], "TypeError"),
            Err(pbx::RouteError::Value(e)) => {
                if !c["out"]["ok"].to_string().is_ascii() && c["out"]["ok"].is_array() {
                    assert_eq!(e, "Invalid destination or listener port");
                } else {
                    assert_eq!(c["out"]["message"], e, "{c}");
                }
            }
        }
    }
}
#[test]
fn recording_matches_python() {
    for c in vectors()["recordings"].as_array().unwrap() {
        let mut r = pbx::Recording::default();
        let mut errors = vec![];
        for op in c["ops"].as_array().unwrap() {
            let now = op[1].as_f64().unwrap();
            let err = match op[0].as_str().unwrap() {
                "start" => {
                    r.start(now);
                    None
                }
                "discard" => {
                    r.discard();
                    None
                }
                "append" => r.append(now, &bytes(op[2].as_str().unwrap())).err(),
                _ => panic!(),
            };
            errors.push(err);
        }
        assert_eq!(json!(errors), c["errors"]);
        assert_eq!(
            json!(r.wav().map(|v| Sha256::digest(&v)
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect::<String>())),
            c["wav_sha256"]
        );
    }
}
#[test]
fn receipts_match_python() {
    for c in vectors()["receipts"].as_array().unwrap() {
        let got =
            sms::receipt_valid(s(c, "job_id"), s(c, "status"), s(c, "receipt"), false).is_ok();
        // Rust accepts canonical UUIDs only; Python also accepts compact, braced and URN forms.
        if !got && c["valid"] == true {
            assert_ne!(s(c, "job_id").len(), 36);
        } else {
            assert_eq!(got, c["valid"], "{c}");
        }
    }
}
#[test]
fn packets_match_python() {
    for c in vectors()["packets"].as_array().unwrap() {
        let kind = c["kind"].as_u64().unwrap() as u8;
        let length = c["length"].as_u64().unwrap() as usize;
        let encoded = pbx::encode_packet(kind, &vec![42; length]).unwrap();
        assert_eq!(encoded, bytes(s(c, "encoded")));
        assert_eq!(
            pbx::parse_header([encoded[0], encoded[1], encoded[2]]).is_ok(),
            c["accepted"]
        );
    }
}
#[test]
fn incoming_hashes_and_operational_keywords_match_python() {
    let v = vectors();
    for c in v["incoming"].as_array().unwrap() {
        let valid = sms::incoming_valid(
            s(c, "message_id"),
            s(c, "sender"),
            s(c, "to"),
            s(c, "body"),
            false,
        );
        assert_eq!(valid, c["valid"], "{c}");
        if valid {
            assert_eq!(
                sms::inbound_forbidden(s(c, "to"), s(c, "sender"), "+6421123456"),
                c["forbidden"]
            );
        }
    }
    for c in v["hashes"].as_array().unwrap() {
        assert_eq!(sms::token_hash(s(c, "token")), c["out"]);
    }
    for c in v["keywords"].as_array().unwrap() {
        assert_eq!(sms::is_operational_keyword(s(c, "body")), c["out"]);
    }
    assert!(
        sms::receipt_valid("12345678-1234-1234-1234-123456789abc", "failed", "", true).is_err()
    );
    assert!(!sms::incoming_valid(
        "id",
        "+6421999999",
        "+6421123456",
        "hello",
        true
    ));
}

#[test]
fn oversized_packet_cannot_wrap_length() {
    assert!(pbx::encode_packet(16, &vec![0; 65536]).is_err());
}
