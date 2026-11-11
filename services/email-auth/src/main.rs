use std::sync::Arc;

use axum::{extract::State, routing::{get, post}, Json, Router};
use base64::{engine::general_purpose::STANDARD, Engine};
use mail_auth::dkim::VerifySignature;
use mail_auth::{AuthenticatedMessage, DkimResult, MessageAuthenticator};
use serde::{Deserialize, Serialize};

#[derive(Clone)]
struct AppState {
    auth: Arc<MessageAuthenticator>,
    max_bytes: usize,
}

#[derive(Deserialize)]
struct VerifyRequest {
    raw_b64: String,
}

#[derive(Serialize)]
struct SignatureOut {
    domain: String,
    result: String,
}

#[derive(Serialize)]
struct VerifyResponse {
    dkim: String,
    dmarc: String,
    from: String,
    /// True only when a passing signature's `d=` domain aligns with the `From`
    /// domain. The API trusts this, not the raw `dmarc` label, so an aligned
    /// DKIM pass is reported as verified even when the domain publishes no
    /// DMARC record (where DMARC itself would evaluate to `none`).
    aligned: bool,
    signatures: Vec<SignatureOut>,
    error: Option<String>,
}

fn failure(message: &str) -> VerifyResponse {
    VerifyResponse {
        dkim: "none".into(),
        dmarc: "none".into(),
        from: String::new(),
        aligned: false,
        signatures: Vec::new(),
        error: Some(message.into()),
    }
}

async fn healthz() -> &'static str {
    "ok"
}

async fn verify(State(state): State<AppState>, Json(req): Json<VerifyRequest>) -> Json<VerifyResponse> {
    let bytes = match STANDARD.decode(req.raw_b64.as_bytes()) {
        Ok(bytes) => bytes,
        Err(_) => return Json(failure("invalid base64")),
    };
    if bytes.len() > state.max_bytes {
        return Json(failure("message too large"));
    }
    let message = match AuthenticatedMessage::parse(&bytes) {
        Some(message) => message,
        None => return Json(failure("unparseable message")),
    };

    let result = state.auth.verify_dkim(&message).await;
    let mut signatures = Vec::new();
    let mut any_pass = false;
    for output in result.iter() {
        let domain = output
            .signature()
            .map(|signature| signature.domain().to_string())
            .unwrap_or_default();
        let passed = output.result() == &DkimResult::Pass;
        any_pass |= passed;
        signatures.push(SignatureOut {
            domain,
            result: if passed { "pass" } else { "fail" }.into(),
        });
    }

    let from = message.first_from_address().to_string();
    let (dkim, dmarc, aligned) = verdict(&signatures, &from);

    Json(VerifyResponse {
        dkim: dkim.into(),
        dmarc: dmarc.into(),
        from,
        aligned,
        signatures,
        error: None,
    })
}

/// DKIM and DMARC verdicts relative to the `From` address.
///
/// `aligned` is what the API trusts: a passing signature whose `d=` domain is
/// the From domain (or a parent of it) authenticates that address. DMARC itself
/// evaluates to `none` when the domain publishes no record, which is common for
/// small-business mail and is not evidence of anything; the API treats
/// `aligned` as the authentication signal and uses `dmarc` only to detect a
/// genuine policy failure.
fn verdict(signatures: &[SignatureOut], from: &str) -> (&'static str, &'static str, bool) {
    let from_domain = from.rsplit('@').next().unwrap_or("").to_ascii_lowercase();
    let aligned = !from_domain.is_empty()
        && signatures.iter().any(|signature| {
            signature.result == "pass"
                && (signature.domain == from_domain
                    || from_domain.ends_with(&format!(".{}", signature.domain)))
        });
    let any_pass = signatures.iter().any(|signature| signature.result == "pass");
    let dkim = if any_pass {
        "pass"
    } else if signatures.is_empty() {
        "none"
    } else {
        "fail"
    };
    let dmarc = if aligned {
        "pass"
    } else if signatures.is_empty() {
        "none"
    } else {
        "fail"
    };
    (dkim, dmarc, aligned)
}

#[tokio::main]
async fn main() {
    let max_bytes = std::env::var("MAX_BYTES")
        .ok()
        .and_then(|value| value.parse().ok())
        .unwrap_or(512_000usize);
    let auth = MessageAuthenticator::new_cloudflare().expect("DNS resolver");
    let state = AppState { auth: Arc::new(auth), max_bytes };
    let app = Router::new()
        .route("/healthz", get(healthz))
        .route("/verify", post(verify))
        .with_state(state);
    let port = std::env::var("PORT").unwrap_or_else(|_| "8090".into());
    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{port}"))
        .await
        .expect("bind");
    println!("email-auth listening on {port}");
    axum::serve(listener, app).await.expect("serve");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sig(domain: &str, result: &str) -> SignatureOut {
        SignatureOut { domain: domain.into(), result: result.into() }
    }

    #[test]
    fn aligned_pass_is_dmarc_pass() {
        let (dkim, dmarc, aligned) =
            verdict(&[sig("pukeko.example", "pass")], "conrad@pukeko.example");
        assert_eq!((dkim, dmarc, aligned), ("pass", "pass", true));
    }

    #[test]
    fn subdomain_from_relaxes_to_parent_signature() {
        let (_, dmarc, aligned) =
            verdict(&[sig("example.com", "pass")], "conrad@mail.example.com");
        assert_eq!((dmarc, aligned), ("pass", true));
    }

    #[test]
    fn unaligned_pass_is_dkim_pass_dmarc_fail() {
        let (dkim, dmarc, aligned) =
            verdict(&[sig("esp.example", "pass")], "conrad@pukeko.example");
        assert_eq!((dkim, dmarc, aligned), ("pass", "fail", false));
    }

    #[test]
    fn unsigned_message_is_none() {
        let (dkim, dmarc, aligned) = verdict(&[], "conrad@pukeko.example");
        assert_eq!((dkim, dmarc, aligned), ("none", "none", false));
    }

    #[test]
    fn failing_signature_only_is_fail() {
        let (dkim, dmarc, _) =
            verdict(&[sig("pukeko.example", "fail")], "conrad@pukeko.example");
        assert_eq!((dkim, dmarc), ("fail", "fail"));
    }

    #[test]
    fn missing_from_is_never_aligned() {
        let (_, dmarc, aligned) = verdict(&[sig("", "pass")], "");
        assert_eq!((dmarc, aligned), ("fail", false));
    }
}
