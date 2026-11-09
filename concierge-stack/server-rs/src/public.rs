//! Batch 40, family 1: public routes whose credential is a path segment (`/api/v1/unsubscribe/{token}`,
//! `/api/v1/voice/recordings/shared/{token}`, `/api/v1/social-media/{token}`). None is under the owner boundary.
use crate::{detail, server_error, unroutable, State};
use axum::async_trait;
use axum::extract::{FromRequestParts, State as AxState};
use axum::http::request::Parts;
use axum::http::{header, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use concierge_core::owner_portal::PortalSettings;
use concierge_core::{social, unsub, voice_records};
use serde_json::json;

/// Settings read only by these routes (`config.py` names, upper-cased).
#[derive(Clone)]
pub struct Extra {
    pub unsubscribe_secret: String,
    pub social_enabled: bool,
    pub social_url: String,
    pub social_key: String,
    pub owner_portal_url: String,
    pub email_drafts_enabled: bool,
    portal: PortalSettings,
}

impl Extra {
    /// The settings the onboarding overview and readiness report read.
    pub fn portal(&self) -> PortalSettings {
        self.portal.clone()
    }

    pub fn from_env() -> Extra {
        let get = |k: &str, d: &str| std::env::var(k).unwrap_or_else(|_| d.to_string());
        let flag = |k: &str| {
            concierge_core::pydantic::parse_bool(&json!(get(k, "false"))).unwrap_or(false)
        };
        let portal = PortalSettings {
            llm_api_key: get("LLM_API_KEY", ""),
            xai_api_key: get("XAI_API_KEY", ""),
            website_verified_tenants: get("WEBSITE_VERIFIED_TENANTS", ""),
            phone_verified_tenants: get("PHONE_VERIFIED_TENANTS", ""),
            phone_receptionist_enabled: flag("PHONE_RECEPTIONIST_ENABLED"),
            phone_voice_provider: get("PHONE_VOICE_PROVIDER", "grok"),
            xai_sip_connections: get("XAI_SIP_CONNECTIONS", ""),
            twilio_auth_token: get("TWILIO_AUTH_TOKEN", ""),
            twilio_account_sid: get("TWILIO_ACCOUNT_SID", ""),
            twilio_from_number: get("TWILIO_FROM_NUMBER", ""),
            twilio_messaging_service_sid: get("TWILIO_MESSAGING_SERVICE_SID", ""),
            public_base_url: get("PUBLIC_BASE_URL", "http://localhost:8000"),
            sms_provider: get("SMS_PROVIDER", "twilio"),
            smsgate_base_url: get("SMSGATE_BASE_URL", ""),
            smsgate_username: get("SMSGATE_USERNAME", ""),
            smsgate_password: get("SMSGATE_PASSWORD", ""),
            smtp_host: get("SMTP_HOST", ""),
            smtp_from: get("SMTP_FROM", ""),
            social_service_enabled: flag("SOCIAL_SERVICE_ENABLED"),
            voice_recording_enabled: flag("VOICE_RECORDING_ENABLED"),
            phone_recording_enabled: flag("PHONE_RECORDING_ENABLED"),
            inbound_cloudflare_enabled: flag("INBOUND_CLOUDFLARE_ENABLED"),
        };
        Extra {
            owner_portal_url: get(
                "OWNER_PORTAL_URL",
                "https://concierge.trendibizz.com/owner-ui",
            ),
            email_drafts_enabled: flag("EMAIL_DRAFTS_ENABLED"),
            portal,
            unsubscribe_secret: get("UNSUBSCRIBE_SECRET", ""),
            social_enabled: concierge_core::pydantic::parse_bool(&json!(get(
                "SOCIAL_SERVICE_ENABLED",
                "false"
            )))
            .unwrap_or(false),
            social_url: get("SOCIAL_SERVICE_URL", "http://127.0.0.1:4390"),
            social_key: get("SOCIAL_CONCIERGE_KEY", ""),
        }
    }
}

pub fn routes() -> Router<State> {
    Router::new()
        .route("/api/v1/unsubscribe/:token", get(unsubscribe_page))
        .route(
            "/api/v1/voice/recordings/shared/:token",
            get(shared_voice_recording),
        )
        .route("/api/v1/social-media/:token", get(social_media_download))
}

fn html(status: u16, body: String) -> Response {
    (
        StatusCode::from_u16(status).unwrap(),
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        body,
    )
        .into_response()
}

/// `GET /api/v1/unsubscribe/{token}`: the confirm page. The secret is `UNSUBSCRIBE_SECRET`, else `ADMIN_TOKEN`.
async fn unsubscribe_page(AxState(state): AxState<State>, Seg(token): Seg) -> Response {
    if let Some(r) = unroutable(&token) {
        return r;
    }
    let extra = &state.0.extra;
    let secret = if extra.unsubscribe_secret.is_empty() {
        state.0.config.admin_token.as_str()
    } else {
        extra.unsubscribe_secret.as_str()
    };
    match unsub::unsubscribe_confirm_page(secret, &token) {
        Ok((status, body)) => html(status, body),
        Err(()) => server_error(),
    }
}

/// `GET /api/v1/voice/recordings/shared/{token}`: the audio of a 24-hour share link, never cached.
async fn shared_voice_recording(AxState(state): AxState<State>, Seg(token): Seg) -> Response {
    if let Some(r) = unroutable(&token) {
        return r;
    }
    let gone = || detail(404, "Recording link expired or unavailable");
    if !(32..=100).contains(&token.chars().count()) {
        return gone();
    }
    let Some(pool) = state.0.pool.as_ref() else {
        return server_error();
    };
    let Ok(client) = pool.get().await else {
        return server_error();
    };
    let digest = voice_records::digest(&token);
    let Ok(row) = client
        .query_opt(
            "SELECT r.audio,r.mime_type FROM voice_recording_shares s JOIN voice_recordings r \
             ON r.session_id=s.session_id AND r.tenant_id=s.tenant_id \
             WHERE s.token_hash=$1 AND s.expires_at>now() AND r.created_at>now()-interval '30 days'",
            &[&digest],
        )
        .await
    else {
        return server_error();
    };
    let Some(row) = row else {
        return gone();
    };
    audio_response(row.get::<_, Vec<u8>>(0), &row.get::<_, String>(1))
}

/// `private_audio_response`. `mime_type.split("/")[1]` raises for a value without a slash (a 500); the table's CHECK
/// constraint keeps it to four audio types, so that branch is only reachable through a schema change.
pub(crate) fn audio_response(audio: Vec<u8>, mime: &str) -> Response {
    let Some(sub) = mime.split('/').nth(1) else {
        return server_error();
    };
    let Ok(ctype) = header::HeaderValue::from_str(mime) else {
        return server_error();
    };
    let filename = format!("inline; filename=\"concierge-recording.{sub}\"");
    let Ok(disposition) = header::HeaderValue::from_str(&filename) else {
        return server_error();
    };
    (
        StatusCode::OK,
        [
            (header::CONTENT_TYPE, ctype),
            (
                header::CACHE_CONTROL,
                header::HeaderValue::from_static("private, no-store"),
            ),
            (
                header::X_CONTENT_TYPE_OPTIONS,
                header::HeaderValue::from_static("nosniff"),
            ),
            (
                header::REFERRER_POLICY,
                header::HeaderValue::from_static("no-referrer"),
            ),
            (
                header::HeaderName::from_static("x-robots-tag"),
                header::HeaderValue::from_static("noindex, nofollow, noarchive"),
            ),
            (header::CONTENT_DISPOSITION, disposition),
        ],
        audio,
    )
        .into_response()
}

/// `GET /api/v1/social-media/{token}`: proxies one public media file from the private social service.
///
/// Ported: the 2048-character token limit and `_configuration()` (503 when the service is off, the key is short or the
/// address is not an approved loopback endpoint). NOT ported: the outbound request to the social service, because this
/// server has no HTTP client and sends nothing anywhere. With a valid configuration the route fails closed with a plain
/// 500 rather than guess what the service would answer.
async fn social_media_download(AxState(state): AxState<State>, Seg(token): Seg) -> Response {
    if let Some(r) = unroutable(&token) {
        return r;
    }
    if token.chars().count() > 2048 {
        return detail(404, "Media unavailable");
    }
    let e = &state.0.extra;
    match social::configuration(e.social_enabled, &e.social_key, &e.social_url) {
        Err(social::Failure::Http(err)) => detail(err.status, &err.detail),
        Err(social::Failure::ValueError) | Ok(_) => server_error(),
    }
}

/// The last path segment (the route's single parameter), decoded the way Starlette decodes it: `urllib.parse.unquote` with `errors="replace"`, so an
/// invalid UTF-8 escape such as `%ff` becomes U+FFFD and the request is routed on. axum's own `Path<String>` answers such a
/// request with a 400, which Python never does.
pub(crate) struct Seg(pub String);

#[async_trait]
impl<S: Send + Sync> FromRequestParts<S> for Seg {
    type Rejection = Response;
    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        // Every route using this has exactly one parameter and it is the last segment; take it from the raw path, because
        // axum has already refused to percent-decode an invalid sequence by the time its own extractors run.
        let raw = parts.uri.path().rsplit('/').next().unwrap_or("");
        Ok(Seg(unquote_replace(raw)))
    }
}

/// The path segment at `N` (0 is the empty text before the first `/`), decoded like [`Seg`]. For routes whose parameter is not last.
pub(crate) struct SegAt<const N: usize>(pub String);

#[async_trait]
impl<S: Send + Sync, const N: usize> FromRequestParts<S> for SegAt<N> {
    type Rejection = Response;
    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let raw = parts.uri.path().split('/').nth(N).unwrap_or("");
        Ok(SegAt(unquote_replace(raw)))
    }
}

pub(crate) fn unquote_replace(raw: &str) -> String {
    let b = raw.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        let hex = |c: u8| (c as char).to_digit(16);
        if b[i] == b'%' && i + 2 < b.len() {
            if let (Some(h), Some(l)) = (hex(b[i + 1]), hex(b[i + 2])) {
                out.push((h * 16 + l) as u8);
                i += 3;
                continue;
            }
        }
        out.push(b[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}
