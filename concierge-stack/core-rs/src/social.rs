//! Port of `social_bridge.py`: the tenant-scoped bridge to the private Rust social service. Configuration is accepted only
//! for an operator-controlled loopback/Docker address, upstream failures are translated to fixed messages (arbitrary
//! provider text is never forwarded), and every operation validates identifiers before it builds a path. The transport
//! (`Api`) is supplied by the caller; this module holds no credentials and contacts nothing.
use crate::pyurl::{hostname, port, urlsplit, userinfo};
use regex::Regex;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::sync::OnceLock;

#[derive(Debug, PartialEq, Eq, Clone)]
pub struct HttpErr {
    pub status: u16,
    pub detail: String,
}

fn http(status: u16, detail: &str) -> HttpErr {
    HttpErr {
        status,
        detail: detail.into(),
    }
}

/// What can go wrong besides an HTTP error: Python raising `ValueError` out of the call.
#[derive(Debug, PartialEq, Eq)]
pub enum Failure {
    Http(HttpErr),
    ValueError,
}

impl From<HttpErr> for Failure {
    fn from(e: HttpErr) -> Failure {
        Failure::Http(e)
    }
}

fn safe_lists() -> &'static (HashSet<String>, HashSet<String>) {
    static T: OnceLock<(HashSet<String>, HashSet<String>)> = OnceLock::new();
    T.get_or_init(|| {
        let v: Value = serde_json::from_str(include_str!("social_safe_errors.json")).unwrap();
        let set = |k: &str| {
            v[k].as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_str().unwrap().to_string())
                .collect()
        };
        (set("safe"), set("safe_linkedin"))
    })
}

fn post_id() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    R.get_or_init(|| Regex::new(r"^[A-Za-z0-9_-]{16,128}$").unwrap())
}

/// `_configuration()`: the service base URL and key, or why it is refused.
pub fn configuration(
    enabled: bool,
    key: &str,
    service_url: &str,
) -> Result<(String, String), Failure> {
    if !enabled {
        return Err(http(503, "Social service is not enabled").into());
    }
    if key.is_empty() || key.chars().count() < 32 {
        return Err(http(503, "Social service credentials are not configured").into());
    }
    let base = service_url.trim_end_matches('/');
    let url = urlsplit(base, "").map_err(|_| Failure::ValueError)?;
    let host = hostname(&url.netloc);
    let (user, pass) = userinfo(&url.netloc);
    let refused = || {
        Failure::Http(http(
            503,
            "Social service address is not an approved internal endpoint",
        ))
    };
    if url.scheme != "http"
        || !matches!(
            host.as_deref(),
            Some("127.0.0.1" | "localhost" | "host.docker.internal")
        )
    {
        return Err(refused());
    }
    // `.port` is only evaluated here, after the cheaper checks, and raises ValueError for a bad port
    let p = port(&url.netloc).map_err(|_| Failure::ValueError)?;
    if p.is_none_or(|p| p < 1024)
        || !url.path.is_empty()
        || !url.query.is_empty()
        || !url.fragment.is_empty()
        || user.is_some_and(|u| !u.is_empty())
        || pass.is_some_and(|x| !x.is_empty())
    {
        return Err(refused());
    }
    Ok((base.to_string(), key.to_string()))
}

/// Per-request timeout in seconds.
pub fn timeout(path: &str) -> f64 {
    if path.ends_with("/media") {
        150.0
    } else if path.ends_with("/compose") {
        75.0
    } else {
        8.0
    }
}

/// Translate the service's answer. `body` is `Err(())` when the response is not JSON.
pub fn response(status: u16, path: &str, body: Result<Value, ()>) -> Result<Value, Failure> {
    if status < 300 {
        return body.map_err(|_| Failure::ValueError);
    }
    let error_text = |body: &Result<Value, ()>| -> Option<String> {
        match body {
            Ok(Value::Object(m)) => m.get("error").and_then(|e| e.as_str().map(String::from)),
            _ => None,
        }
    };
    if status == 404 {
        return Err(http(404, "Social resource not found").into());
    }
    if status == 400 && path.contains("/oauth/meta/") {
        let msg = error_text(&body).filter(|m| safe_lists().0.contains(m));
        return Err(http(
            400,
            msg.as_deref()
                .unwrap_or("Meta authorization could not be completed"),
        )
        .into());
    }
    if status == 400 && path.contains("/oauth/linkedin/") {
        let msg = error_text(&body).filter(|m| safe_lists().1.contains(m));
        return Err(http(
            400,
            msg.as_deref()
                .unwrap_or("LinkedIn authorization could not be completed"),
        )
        .into());
    }
    if status == 400 {
        return Err(http(400, "Social request could not be completed").into());
    }
    if status == 409 {
        return Err(http(409, "Social action conflicts with its current state").into());
    }
    Err(http(502, "Social service rejected request").into())
}

pub trait Api {
    fn request(&mut self, method: &str, path: &str, data: Option<Value>) -> Result<Value, HttpErr>;
}

/// `ensure_tenant`: make sure the business exists in the service, tolerating a creation race only when the exact tenant
/// can then be read back.
pub fn ensure_tenant(api: &mut dyn Api, slug: &str, name: &str) -> Result<String, HttpErr> {
    static SLUG: OnceLock<Regex> = OnceLock::new();
    if !SLUG
        .get_or_init(|| Regex::new(r"^[a-z0-9][a-z0-9-]{0,100}$").unwrap())
        .is_match(slug)
    {
        return Err(http(400, "Invalid tenant slug"));
    }
    let rules = format!("/v1/customers/{slug}/rules");
    match api.request("GET", &rules, None) {
        Ok(_) => {}
        Err(e) if e.status != 404 => return Err(e),
        Err(_) => {
            let create = api.request(
                "POST",
                "/v1/customers",
                Some(json!({"id": slug, "name": name, "approval_contact": ""})),
            );
            if let Err(e) = create {
                if e.status != 400 && e.status != 409 {
                    return Err(e);
                }
                api.request("GET", &rules, None)?;
            }
        }
    }
    Ok(slug.to_string())
}

fn valid_id(s: &str) -> bool {
    post_id().is_match(s)
}

fn s_arg(args: &[Value], i: usize) -> &str {
    args[i].as_str().unwrap_or("")
}

/// Run one bridge operation by its Python function name. `args` are the arguments after `tenant`.
pub fn run(
    api: &mut dyn Api,
    slug: &str,
    name: &str,
    op: &str,
    args: &[Value],
) -> Result<Value, HttpErr> {
    let oauth_providers = [
        "tiktok",
        "google",
        "x",
        "mastodon",
        "linkedin",
        "linkedin_organization",
    ];
    // validation happens before the tenant is provisioned for some operations and after for others; this mirrors each one
    let ensure = |api: &mut dyn Api| ensure_tenant(api, slug, name);
    let callback_ok = |state: &str, code: &str| {
        valid_id(state) && !code.is_empty() && code.chars().count() <= 2048
    };
    match op {
        "ensure_tenant" => ensure(api).map(Value::from),
        "provider_status" => api.request("GET", "/v1/oauth/providers", None),
        "accounts" | "posts" => {
            let s = ensure(api)?;
            api.request("GET", &format!("/v1/customers/{s}/{op}"), None)
        }
        "compose" => {
            let s = ensure(api)?;
            api.request(
                "POST",
                &format!("/v1/customers/{s}/compose"),
                Some(args[0].clone()),
            )
        }
        "create_draft" => {
            let s = ensure(api)?;
            let content = s_arg(args, 0);
            let ids: Vec<&str> = args[1]
                .as_array()
                .map(|a| a.iter().map(|x| x.as_str().unwrap_or("")).collect())
                .unwrap_or_default();
            if crate::py_strip(content).is_empty()
                || content.chars().count() > 10000
                || !(1..=10).contains(&ids.len())
            {
                return Err(http(
                    400,
                    "A valid post and one or more accounts are required",
                ));
            }
            if ids.iter().any(|a| !valid_id(a)) {
                return Err(http(400, "Invalid account identifier"));
            }
            let media: Vec<Value> = args[4].as_array().cloned().unwrap_or_default();
            static UPLOAD: OnceLock<Regex> = OnceLock::new();
            let upload =
                UPLOAD.get_or_init(|| Regex::new(r"^upload:[A-Za-z0-9_-]{20,128}$").unwrap());
            let bad_media = media.len() > 10
                || media.iter().any(|m| match m.as_str() {
                    Some(t) => {
                        t.chars().count() > 2048
                            || !(t.starts_with("https://") || upload.is_match(t))
                    }
                    None => true,
                });
            if bad_media {
                return Err(http(400, "Only HTTPS media URLs are allowed"));
            }
            let options = if crate::pyval::truthy(Some(&args[5])) {
                args[5].clone()
            } else {
                json!({})
            };
            api.request(
                "POST",
                &format!("/v1/customers/{s}/posts"),
                Some(json!({"content": content, "account_ids": ids, "link": args[2], "hashtags": args[3], "media": media, "options": options})),
            )
        }
        "submit_draft" | "request_approval" | "decide" => {
            let s = ensure(api)?;
            let id = s_arg(args, 0);
            if !valid_id(id) {
                return Err(http(
                    400,
                    if op == "decide" {
                        "Invalid approval token"
                    } else {
                        "Invalid post identifier"
                    },
                ));
            }
            match op {
                "submit_draft" => api.request(
                    "POST",
                    &format!("/v1/customers/{s}/posts/{id}/submit"),
                    None,
                ),
                "request_approval" => api.request(
                    "POST",
                    &format!("/v1/customers/{s}/posts/{id}/approval-request"),
                    Some(json!({"scheduled_at": args[1]})),
                ),
                _ => api.request(
                    "POST",
                    &format!(
                        "/v1/customers/{s}/approvals/{id}/{}",
                        if args[1].as_bool() == Some(true) {
                            "approve"
                        } else {
                            "reject"
                        }
                    ),
                    None,
                ),
            }
        }
        "renew_social_token" => {
            if !valid_id(s_arg(args, 0)) {
                return Err(http(400, "Invalid social account"));
            }
            let s = ensure(api)?;
            api.request(
                "POST",
                &format!("/v1/customers/{s}/oauth/renew/{}", s_arg(args, 0)),
                None,
            )
        }
        "start_meta_oauth" | "finish_meta_oauth" | "unlink_meta" => {
            let net = s_arg(args, 0);
            let known = matches!(net, "facebook" | "instagram");
            match op {
                "start_meta_oauth" => {
                    if !known {
                        return Err(http(400, "Unsupported social network"));
                    }
                    let s = ensure(api)?;
                    api.request(
                        "POST",
                        &format!("/v1/customers/{s}/oauth/meta/{net}/start"),
                        None,
                    )
                }
                "finish_meta_oauth" => {
                    if !known {
                        return Err(http(400, "Unsupported social network"));
                    }
                    if !callback_ok(s_arg(args, 1), s_arg(args, 2)) {
                        return Err(http(400, "Invalid OAuth callback"));
                    }
                    let s = ensure(api)?;
                    api.request(
                        "POST",
                        &format!("/v1/customers/{s}/oauth/meta/{net}/finish"),
                        Some(json!({"state": args[1], "code": args[2]})),
                    )
                }
                _ => {
                    if !known || !valid_id(s_arg(args, 1)) {
                        return Err(http(400, "Invalid social account"));
                    }
                    let s = ensure(api)?;
                    api.request(
                        "DELETE",
                        &format!(
                            "/v1/customers/{s}/oauth/meta/{net}/accounts/{}",
                            s_arg(args, 1)
                        ),
                        None,
                    )
                }
            }
        }
        _ => {
            // start_<p>_oauth / finish_<p>_oauth / disconnect_<p> / unlink_linkedin
            if let Some(p) = op
                .strip_prefix("start_")
                .and_then(|r| r.strip_suffix("_oauth"))
                .filter(|p| oauth_providers.contains(p))
            {
                let s = ensure(api)?;
                return api.request("POST", &format!("/v1/customers/{s}/oauth/{p}/start"), None);
            }
            if let Some(p) = op
                .strip_prefix("finish_")
                .and_then(|r| r.strip_suffix("_oauth"))
                .filter(|p| oauth_providers.contains(p))
            {
                let validate_first = matches!(p, "tiktok" | "google" | "x");
                let s = if validate_first {
                    if !callback_ok(s_arg(args, 0), s_arg(args, 1)) {
                        return Err(http(400, "Invalid OAuth callback"));
                    }
                    ensure(api)?
                } else {
                    let s = ensure(api)?;
                    if !callback_ok(s_arg(args, 0), s_arg(args, 1)) {
                        return Err(http(400, "Invalid OAuth callback"));
                    }
                    s
                };
                return api.request(
                    "POST",
                    &format!("/v1/customers/{s}/oauth/{p}/finish"),
                    Some(json!({"state": args[0], "code": args[1]})),
                );
            }
            let provider = match op {
                "disconnect_tiktok" => "tiktok",
                "disconnect_google" => "google",
                "disconnect_x" => "x",
                "disconnect_mastodon" => "mastodon",
                "unlink_linkedin" => "linkedin",
                other => panic!("unknown operation {other}"),
            };
            let id = s_arg(args, 0);
            let s = if matches!(provider, "tiktok" | "google" | "x") {
                if !valid_id(id) {
                    return Err(http(400, "Invalid account identifier"));
                }
                ensure(api)?
            } else {
                let s = ensure(api)?;
                if !valid_id(id) {
                    return Err(http(400, "Invalid account identifier"));
                }
                s
            };
            api.request(
                "DELETE",
                &format!("/v1/customers/{s}/oauth/{provider}/accounts/{id}"),
                None,
            )
        }
    }
}
