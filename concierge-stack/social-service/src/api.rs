//! Loopback JSON API. Concierge key can approve; Hermes agent key cannot.
use crate::{
    guardrails::{check_post, PostInput, Rules},
    model::{NewPost, Post},
    store::Store,
    vault::Vault,
};
use axum::{
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    routing::{get, post, put},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

#[derive(Clone)]
pub struct AppState {
    pub store: Arc<Store>,
    pub vault: Arc<Vault>,
    pub concierge_key: String,
    pub agent_key: String,
}
type ApiResult<T> = Result<Json<T>, (StatusCode, Json<ErrorBody>)>;
#[derive(Serialize)]
pub struct ErrorBody {
    error: String,
}
fn err(status: StatusCode, msg: impl Into<String>) -> (StatusCode, Json<ErrorBody>) {
    (status, Json(ErrorBody { error: msg.into() }))
}
fn server_err(msg: String) -> (StatusCode, Json<ErrorBody>) {
    // Never send SQL, third-party error bodies, or internal credential details
    // to the customer. Only emit a small, explicit set of expected errors.
    if msg == "Customer not found" || msg == "Post not found" {
        return err(StatusCode::NOT_FOUND, "Social resource not found");
    }
    if msg.contains("Conflict")
        || msg.contains("not a draft")
        || msg.contains("Not a draft")
        || msg.contains("Post must be pending")
        || msg.contains("used or expired")
        || msg.contains("not publishing")
        || msg.contains("Invalid transition")
    {
        return err(
            StatusCode::CONFLICT,
            "Social action conflicts with current state",
        );
    }
    // Meta OAuth has several *expected* operator-actionable failures.
    // Return only static, audited descriptions. Never forward provider JSON,
    // raw SQL, authorization codes, access tokens or internal HTTP errors.
    // Fixed, audited LinkedIn errors: no upstream bodies, codes or tokens.
    const LINKEDIN_USER_ERRORS: &[&str] = &[
        "LinkedIn authorization was rejected",
        "Invalid LinkedIn OAuth token response",
        "Invalid LinkedIn OAuth token expiry",
        "LinkedIn did not grant the requested permissions",
        "LinkedIn profile lookup unavailable",
        "LinkedIn profile verification failed",
        "Invalid LinkedIn profile",
        "LinkedIn profile missing identity",
        "OAuth state expired or invalid",
        "LinkedIn authorization unavailable",
    ];
    if LINKEDIN_USER_ERRORS.contains(&msg.as_str()) {
        return err(StatusCode::BAD_REQUEST, msg);
    }
    const META_USER_ERRORS: &[&str] = &[
        "TikTok token exchange unavailable",
        "TikTok token exchange rejected",
        "Invalid TikTok token response",
        "TikTok did not grant valid account access",
        "TikTok profile verification unavailable",
        "TikTok profile verification rejected",
        "Invalid TikTok profile response",
        "TikTok identity mismatch",
        "Facebook authorization rejected",
        "Facebook long-lived token rejected",
        "Facebook permissions not verified",
        "Facebook Page permissions not granted",
        "Facebook Page lookup rejected",
        "No authorized Facebook Pages found",
        "Facebook Page lacks content management access",
        "Meta authorization rejected",
        "Meta long-lived token rejected",
        "Meta permission lookup rejected",
        "Instagram Graph API permissions not granted",
        "Meta connected Pages rejected",
        "No linked professional Instagram account found",
        "No authorized Facebook Pages returned for Instagram",
        "Meta business Page discovery unavailable",
        "Meta business Page discovery invalid",
        "Meta business Page pagination requires review",
        "Meta returned Page without usable Page access token",
        "Meta denied access to selected business Page",
        "Meta business_management permission missing for Page discovery",
        "Instagram Page link query unavailable",
        "Instagram Page link response invalid",
        "Instagram Page link identity mismatch",
        "Facebook Pages lack Instagram management permissions",
        "Facebook Page returned without accessible Instagram professional link",
        "Instagram professional identity lookup unavailable",
        "Instagram professional identity mismatch",
        "Instagram professional identity not verified",
        "Instagram professional identity response invalid",
        "Linked Instagram account is not a verified professional account",
        "Meta access token missing",
        "Meta token validation failed",
        "Meta token belongs to another application",
        "Meta token is expired",
        "Meta token has invalid expiry",
        "Too many selected Facebook Pages for safe discovery",
        "Linked Instagram Page lacks content management access",
        "Facebook account has too many Pages; pagination not yet supported",
        "Meta Page pagination requires operator review",
        "OAuth state expired or invalid",
        "Facebook authorization unavailable",
        "Facebook token invalid",
        "Facebook token missing",
        "Facebook long-lived token unavailable",
        "Facebook long-lived token invalid",
        "Facebook long-lived token missing expiry",
        "Facebook permission check unavailable",
        "Facebook permission response invalid",
        "Facebook Page lookup unavailable",
        "Facebook Page list invalid",
        "Meta authorization unavailable",
        "Invalid Meta token",
        "Meta token missing",
        "Meta long-lived exchange unavailable",
        "Invalid Meta long-lived token",
        "Meta token missing expiry",
        "Meta permissions unavailable",
        "Meta permission response invalid",
        "Meta connected Pages lookup unavailable",
        "Invalid Meta Pages response",
        "Meta Page pagination requires operator review",
        "Instagram authorization unavailable",
        "Instagram authorization rejected",
        "Invalid Instagram token response",
        "Instagram access token missing",
        "Instagram long-lived exchange unavailable",
        "Instagram long-lived token rejected",
        "Instagram long-lived token invalid",
        "Instagram long-lived token missing expiry",
        "Instagram profile unavailable",
        "Instagram identity not verified",
        "Invalid Instagram profile",
    ];
    if META_USER_ERRORS.contains(&msg.as_str()) {
        return err(StatusCode::BAD_REQUEST, msg);
    }
    if msg.contains("Guardrails blocked") {
        return err(
            StatusCode::UNPROCESSABLE_ENTITY,
            "Social post did not pass content rules",
        );
    }
    err(
        StatusCode::BAD_REQUEST,
        "Social request could not be completed",
    )
}

fn constant_time(a: &str, b: &str) -> bool {
    let a = a.as_bytes();
    let b = b.as_bytes();
    let mut bad = a.len() ^ b.len();
    for i in 0..a.len().max(b.len()) {
        bad |= usize::from(a.get(i).copied().unwrap_or(0) ^ b.get(i).copied().unwrap_or(0));
    }
    bad == 0
}
fn role(
    h: &HeaderMap,
    s: &AppState,
    owner: bool,
    customer: Option<&str>,
) -> Result<(), (StatusCode, Json<ErrorBody>)> {
    let auth = h
        .get(axum::http::header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .unwrap_or("");
    if auth.is_empty() {
        return Err(err(StatusCode::UNAUTHORIZED, "Missing bearer key"));
    }
    if constant_time(auth, &s.concierge_key) {
        return Ok(());
    }
    // Legacy global agent key must not authorize any customer-specific operation.
    if constant_time(auth, &s.agent_key) {
        return Err(err(
            StatusCode::FORBIDDEN,
            "Global Hermes key has no tenant permissions; use a tenant agent key",
        ));
    }
    if !owner && customer.is_some_and(|c| s.store.verify_agent_key(c, auth)) {
        return Ok(());
    }
    Err(err(
        StatusCode::FORBIDDEN,
        "Not authorized for this customer",
    ))
}

#[derive(Serialize)]
struct Health {
    ok: bool,
}
async fn health() -> Json<Health> {
    Json(Health { ok: true })
}

#[derive(Serialize)]
struct OAuthProviders {
    linkedin: bool,
    mastodon: bool,
    facebook: bool,
    instagram: bool,
    google_business: bool,
    tiktok: bool,
    callback_path: &'static str,
}

async fn oauth_providers(State(s): State<AppState>, h: HeaderMap) -> ApiResult<OAuthProviders> {
    role(&h, &s, true, None)?;
    let callback_path = "/owner/social/oauth/callback";
    // Report configured only when the registered redirect targets the real
    // same-origin Concierge callback. Never expose secrets or client IDs.
    let linkedin = crate::linkedin::from_env().is_ok_and(|cfg| {
        reqwest::Url::parse(&cfg.callback).is_ok_and(|url| url.path() == callback_path)
    });
    let mastodon = crate::oauth::from_env().is_ok_and(|cfg| {
        reqwest::Url::parse(&cfg.callback).is_ok_and(|url| url.path() == callback_path)
    });
    Ok(Json(OAuthProviders {
        linkedin,
        mastodon,
        facebook: crate::meta::from_env("facebook").is_ok(),
        instagram: crate::meta::from_env("instagram").is_ok(),
        google_business: crate::google_business::from_env().is_ok(),
        tiktok: crate::tiktok::from_env().is_ok(),
        callback_path,
    }))
}
#[derive(Deserialize)]
pub struct CreateCustomer {
    id: String,
    name: String,
    approval_contact: String,
}
async fn new_customer(
    State(s): State<AppState>,
    h: HeaderMap,
    Json(input): Json<CreateCustomer>,
) -> ApiResult<Health> {
    role(&h, &s, true, None)?;
    s.store
        .create_customer(&input.id, &input.name, &input.approval_contact)
        .map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}
async fn get_rules(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<Rules> {
    role(&h, &s, false, Some(&c))?;
    Ok(Json(s.store.rules(&c).map_err(server_err)?))
}
async fn set_rules(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<Rules>,
) -> ApiResult<Health> {
    role(&h, &s, true, Some(&c))?;
    s.store.update_rules(&c, &input).map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}
async fn check(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<PostInputJson>,
) -> ApiResult<crate::guardrails::Check> {
    role(&h, &s, false, Some(&c))?;
    let rules = s.store.rules(&c).map_err(server_err)?;
    let post = PostInput {
        content: input.content,
        link: input.link,
        hashtags: input.hashtags,
        networks: input.networks,
        media_count: input.media_count,
    };
    Ok(Json(check_post(&post, &rules)))
}
#[derive(Deserialize)]
pub struct PostInputJson {
    content: String,
    #[serde(default)]
    link: String,
    #[serde(default)]
    hashtags: String,
    networks: Vec<String>,
    #[serde(default)]
    media_count: usize,
}
async fn new_post(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<NewPost>,
) -> ApiResult<Post> {
    role(&h, &s, false, Some(&c))?;
    Ok(Json(s.store.create_post(&c, input).map_err(server_err)?))
}
async fn list_posts(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<Vec<Post>> {
    role(&h, &s, false, Some(&c))?;
    Ok(Json(s.store.list_posts(&c).map_err(server_err)?))
}
async fn update_post(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
    Json(input): Json<Edit>,
) -> ApiResult<Post> {
    role(&h, &s, false, Some(&c))?;
    Ok(Json(
        s.store
            .edit_post(&c, &id, input.content)
            .map_err(server_err)?,
    ))
}
#[derive(Deserialize)]
pub struct Edit {
    content: String,
}
async fn submit(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Post> {
    role(&h, &s, false, Some(&c))?;
    Ok(Json(s.store.submit(&c, &id).map_err(server_err)?))
}
async fn accounts(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<Vec<crate::model::Account>> {
    role(&h, &s, false, Some(&c))?;
    Ok(Json(s.store.list_accounts(&c).map_err(server_err)?))
}
#[derive(Deserialize)]
pub struct NewAccount {
    network: String,
    external_id: String,
    display_name: String,
    access_token: String,
    refresh_token: Option<String>,
}
#[derive(Serialize)]
pub struct AccountId {
    id: String,
}
async fn add_account(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(a): Json<NewAccount>,
) -> ApiResult<AccountId> {
    role(&h, &s, true, Some(&c))?;
    let label = crate::vault::account_label(&c, &a.network, &a.external_id);
    let sealed = s.vault.seal(&a.access_token, &label).map_err(server_err)?;
    let refresh = a
        .refresh_token
        .as_deref()
        .map(|token| s.vault.seal(token, &label))
        .transpose()
        .map_err(server_err)?;
    let id = s
        .store
        .add_account(
            &c,
            &a.network,
            &a.external_id,
            &a.display_name,
            &sealed,
            refresh.as_deref(),
        )
        .map_err(server_err)?;
    Ok(Json(AccountId { id }))
}
#[derive(Deserialize)]
pub struct ApprovalRequest {
    scheduled_at: i64,
}
#[derive(Serialize)]
pub struct ApprovalResponse {
    token: String,
    post_id: String,
    revision: u64,
    exact_text: String,
}
async fn approval_request(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
    Json(input): Json<ApprovalRequest>,
) -> ApiResult<ApprovalResponse> {
    role(&h, &s, true, Some(&c))?;
    let p = s.store.get_post(&c, &id).map_err(server_err)?;
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    let token = s
        .store
        .create_approval(&c, &id, input.scheduled_at, now + 3600)
        .map_err(server_err)?;
    Ok(Json(ApprovalResponse {
        token,
        post_id: id,
        revision: p.revision,
        exact_text: format!(
            "{}{}{}{}{}",
            p.content,
            if p.link.is_empty() { "" } else { "\n" },
            p.link,
            if p.hashtags.is_empty() { "" } else { "\n" },
            p.hashtags
        ),
    }))
}
async fn approve(
    State(s): State<AppState>,
    Path((c, token)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Post> {
    role(&h, &s, true, Some(&c))?;
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    Ok(Json(
        s.store.decide(&c, &token, true, now).map_err(server_err)?,
    ))
}
async fn reject(
    State(s): State<AppState>,
    Path((c, token)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Post> {
    role(&h, &s, true, Some(&c))?;
    let now = time::OffsetDateTime::now_utc().unix_timestamp();
    Ok(Json(
        s.store.decide(&c, &token, false, now).map_err(server_err)?,
    ))
}

#[derive(Serialize)]
pub struct AgentCredential {
    token: String,
}
async fn rotate_agent_key(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<AgentCredential> {
    role(&h, &s, true, Some(&c))?;
    let token = s.store.rotate_agent_key(&c).map_err(server_err)?;
    Ok(Json(AgentCredential { token }))
}

#[derive(Deserialize)]
pub struct OAuthFinish {
    state: String,
    code: String,
}
#[derive(Serialize)]
pub struct OAuthLinked {
    account_id: String,
}
async fn oauth_start(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<crate::oauth::Start> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::oauth::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "OAuth linking not configured",
        )
    })?;
    Ok(Json(
        crate::oauth::start(&s.store, &s.vault, &c, &cfg).map_err(server_err)?,
    ))
}
async fn oauth_finish(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<OAuthFinish>,
) -> ApiResult<OAuthLinked> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::oauth::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "OAuth linking not configured",
        )
    })?;
    let account_id = crate::oauth::finish(&s.store, &s.vault, &c, &cfg, &input.state, &input.code)
        .await
        .map_err(server_err)?;
    Ok(Json(OAuthLinked { account_id }))
}

async fn oauth_disconnect(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Health> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::oauth::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "OAuth linking not configured",
        )
    })?;
    crate::oauth::disconnect(&s.store, &s.vault, &c, &id, &cfg)
        .await
        .map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}

async fn linkedin_oauth_start(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<crate::oauth::Start> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::linkedin::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "LinkedIn OAuth not configured",
        )
    })?;
    Ok(Json(
        crate::linkedin::start(&s.store, &s.vault, &c, &cfg).map_err(server_err)?,
    ))
}
async fn linkedin_oauth_finish(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<OAuthFinish>,
) -> ApiResult<OAuthLinked> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::linkedin::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "LinkedIn OAuth not configured",
        )
    })?;
    let account_id =
        crate::linkedin::finish(&s.store, &s.vault, &c, &cfg, &input.state, &input.code)
            .await
            .map_err(server_err)?;
    Ok(Json(OAuthLinked { account_id }))
}

async fn linkedin_disconnect(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Health> {
    role(&h, &s, true, Some(&c))?;
    let (network, _, _, _) = s.store.account(&c, &id).map_err(server_err)?;
    if network != "linkedin" {
        return Err(err(StatusCode::BAD_REQUEST, "Account is not LinkedIn"));
    }
    // No documented general-purpose LinkedIn provider token revocation endpoint.
    // Remove only local credentials. The customer should separately revoke
    // their authorization in LinkedIn's connected-app settings.
    s.store.disconnect_account(&c, &id).map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}

async fn meta_oauth_start(
    State(s): State<AppState>,
    Path((c, network)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<crate::oauth::Start> {
    role(&h, &s, true, Some(&c))?;
    let kind = match network.as_str() {
        "instagram" => "instagram",
        "facebook" => "facebook",
        _ => return Err(err(StatusCode::NOT_FOUND, "Unsupported social network")),
    };
    let cfg = crate::meta::from_env(kind)
        .map_err(|_| err(StatusCode::SERVICE_UNAVAILABLE, "Meta OAuth not configured"))?;
    Ok(Json(
        crate::meta::start(&s.store, &s.vault, &c, &cfg).map_err(server_err)?,
    ))
}
#[derive(Serialize)]
struct MetaAccounts {
    account_ids: Vec<String>,
}
async fn meta_oauth_finish(
    State(s): State<AppState>,
    Path((c, network)): Path<(String, String)>,
    h: HeaderMap,
    Json(input): Json<OAuthFinish>,
) -> ApiResult<MetaAccounts> {
    role(&h, &s, true, Some(&c))?;
    let kind = match network.as_str() {
        "instagram" => "instagram",
        "facebook" => "facebook",
        _ => return Err(err(StatusCode::NOT_FOUND, "Unsupported social network")),
    };
    let cfg = crate::meta::from_env(kind)
        .map_err(|_| err(StatusCode::SERVICE_UNAVAILABLE, "Meta OAuth not configured"))?;
    Ok(Json(MetaAccounts {
        account_ids: crate::meta::finish(&s.store, &s.vault, &c, &cfg, &input.state, &input.code)
            .await
            .map_err(server_err)?,
    }))
}
async fn meta_oauth_disconnect(
    State(s): State<AppState>,
    Path((c, network, id)): Path<(String, String, String)>,
    h: HeaderMap,
) -> ApiResult<Health> {
    role(&h, &s, true, Some(&c))?;
    if network != "facebook" && network != "instagram" {
        return Err(err(StatusCode::NOT_FOUND, "Unsupported social network"));
    }
    crate::meta::disconnect(&s.store, &c, &id, &network).map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}

async fn tiktok_oauth_start(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<crate::oauth::Start> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::tiktok::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "TikTok OAuth not configured",
        )
    })?;
    Ok(Json(
        crate::tiktok::start(&s.store, &s.vault, &c, &cfg).map_err(server_err)?,
    ))
}
async fn tiktok_oauth_finish(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<OAuthFinish>,
) -> ApiResult<MetaAccounts> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::tiktok::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "TikTok OAuth not configured",
        )
    })?;
    let id = crate::tiktok::finish(&s.store, &s.vault, &c, &cfg, &input.state, &input.code)
        .await
        .map_err(server_err)?;
    Ok(Json(MetaAccounts {
        account_ids: vec![id],
    }))
}
async fn tiktok_oauth_disconnect(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Health> {
    role(&h, &s, true, Some(&c))?;
    crate::tiktok::disconnect(&s.store, &c, &id).map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}
async fn google_oauth_start(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
) -> ApiResult<crate::oauth::Start> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::google_business::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "Google OAuth not configured",
        )
    })?;
    Ok(Json(
        crate::google_business::start(&s.store, &s.vault, &c, &cfg).map_err(server_err)?,
    ))
}
async fn google_oauth_finish(
    State(s): State<AppState>,
    Path(c): Path<String>,
    h: HeaderMap,
    Json(input): Json<OAuthFinish>,
) -> ApiResult<MetaAccounts> {
    role(&h, &s, true, Some(&c))?;
    let cfg = crate::google_business::from_env().map_err(|_| {
        err(
            StatusCode::SERVICE_UNAVAILABLE,
            "Google OAuth not configured",
        )
    })?;
    let account_ids =
        crate::google_business::finish(&s.store, &s.vault, &c, &cfg, &input.state, &input.code)
            .await
            .map_err(server_err)?;
    Ok(Json(MetaAccounts { account_ids }))
}
async fn google_oauth_disconnect(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Health> {
    role(&h, &s, true, Some(&c))?;
    crate::google_business::disconnect(&s.store, &c, &id).map_err(server_err)?;
    Ok(Json(Health { ok: true }))
}

#[derive(Serialize)]
struct Renewal {
    expires_at: i64,
}
async fn oauth_renew(
    State(s): State<AppState>,
    Path((c, id)): Path<(String, String)>,
    h: HeaderMap,
) -> ApiResult<Renewal> {
    role(&h, &s, true, Some(&c))?;
    let expires_at = crate::token_refresh::refresh(&s.store, &s.vault, &c, &id)
        .await
        .map_err(server_err)?;
    Ok(Json(Renewal { expires_at }))
}

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(health))
        .route("/v1/oauth/providers", get(oauth_providers))
        .route(
            "/v1/customers/:c/oauth/google/start",
            post(google_oauth_start),
        )
        .route(
            "/v1/customers/:c/oauth/google/finish",
            post(google_oauth_finish),
        )
        .route(
            "/v1/customers/:c/oauth/google/accounts/:id",
            axum::routing::delete(google_oauth_disconnect),
        )
        .route(
            "/v1/customers/:c/oauth/tiktok/start",
            post(tiktok_oauth_start),
        )
        .route(
            "/v1/customers/:c/oauth/tiktok/finish",
            post(tiktok_oauth_finish),
        )
        .route(
            "/v1/customers/:c/oauth/tiktok/accounts/:id",
            axum::routing::delete(tiktok_oauth_disconnect),
        )
        .route("/v1/customers/:c/oauth/renew/:id", post(oauth_renew))
        .route(
            "/v1/customers/:c/oauth/meta/:network/start",
            post(meta_oauth_start),
        )
        .route(
            "/v1/customers/:c/oauth/meta/:network/finish",
            post(meta_oauth_finish),
        )
        .route(
            "/v1/customers/:c/oauth/meta/:network/accounts/:id",
            axum::routing::delete(meta_oauth_disconnect),
        )
        .route("/v1/customers", post(new_customer))
        .route("/v1/customers/:c/agent-key", post(rotate_agent_key))
        .route("/v1/customers/:c/rules", get(get_rules).put(set_rules))
        .route("/v1/customers/:c/check", post(check))
        .route("/v1/customers/:c/posts", get(list_posts).post(new_post))
        .route("/v1/customers/:c/posts/:id", put(update_post))
        .route("/v1/customers/:c/posts/:id/submit", post(submit))
        .route("/v1/customers/:c/accounts", get(accounts).post(add_account))
        .route(
            "/v1/customers/:c/oauth/linkedin/start",
            post(linkedin_oauth_start),
        )
        .route(
            "/v1/customers/:c/oauth/linkedin/finish",
            post(linkedin_oauth_finish),
        )
        .route(
            "/v1/customers/:c/oauth/linkedin/accounts/:id",
            axum::routing::delete(linkedin_disconnect),
        )
        .route("/v1/customers/:c/oauth/mastodon/start", post(oauth_start))
        .route("/v1/customers/:c/oauth/mastodon/finish", post(oauth_finish))
        .route(
            "/v1/customers/:c/oauth/mastodon/accounts/:id",
            axum::routing::delete(oauth_disconnect),
        )
        .route(
            "/v1/customers/:c/posts/:id/approval-request",
            post(approval_request),
        )
        .route("/v1/customers/:c/approvals/:token/approve", post(approve))
        .route("/v1/customers/:c/approvals/:token/reject", post(reject))
        .with_state(state)
}
