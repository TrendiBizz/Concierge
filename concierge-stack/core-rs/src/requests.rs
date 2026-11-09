//! Port of the HTTP request models and small pure helpers in `main.py`: field types, constraints, defaults and validators for
//! 31 request bodies (pydantic lax mode), the allowed-origin decision, rate-limit ordering, money and TwiML text, the admin
//! snippet URLs and the private-audio headers. No route runs here and nothing is sent.
use crate::pydantic::{err, parse_bool, parse_int, FieldErr};
use crate::pyurl::{urlsplit, Fail};
use crate::{owner_profile, py_strip, scoring};
use regex::Regex;
use serde_json::{json, Map, Value};

#[derive(Clone)]
pub enum Ty {
    Str {
        min: usize,
        max: Option<usize>,
        pat: Option<&'static str>,
    },
    Int {
        ge: Option<i64>,
        le: Option<i64>,
    },
    Bool,
    Lit(&'static [&'static str]),
    True,
    ListStr {
        min: usize,
        max: Option<usize>,
    },
    ListLit(&'static [&'static str]),
    DictStr,
    Dict,
    Uuid,
    Datetime,
    Hours,
    Scoring,
    Tz,
    Template,
}

#[derive(Clone)]
pub struct Fd {
    pub name: &'static str,
    pub ty: Ty,
    pub nullable: bool,
    /// `None` means required.
    pub default: Option<Value>,
}

const STATUSES: &[&str] = &["new", "contacted", "booked", "won", "lost"];

fn s(name: &'static str) -> Fd {
    Fd {
        name,
        ty: Ty::Str {
            min: 0,
            max: None,
            pat: None,
        },
        nullable: false,
        default: None,
    }
}
impl Fd {
    fn len(mut self, min: usize, max: usize) -> Fd {
        if let Ty::Str { min: m, max: x, .. } | Ty::ListStr { min: m, max: x } = &mut self.ty {
            *m = min;
            *x = (max > 0).then_some(max);
        }
        self
    }
    fn pat(mut self, p: &'static str) -> Fd {
        if let Ty::Str { pat, .. } = &mut self.ty {
            *pat = Some(p);
        }
        self
    }
    fn opt(mut self) -> Fd {
        self.nullable = true;
        self.default = Some(Value::Null);
        self
    }
    fn dflt(mut self, v: Value) -> Fd {
        self.default = Some(v);
        self
    }
    fn of(name: &'static str, ty: Ty) -> Fd {
        Fd {
            name,
            ty,
            nullable: false,
            default: None,
        }
    }
    fn int(name: &'static str, ge: i64, le: i64) -> Fd {
        Fd::of(
            name,
            Ty::Int {
                ge: Some(ge),
                le: Some(le),
            },
        )
    }
}

/// `(fields, extra="forbid")` for a request model, or `None` for an unknown name.
pub fn model(name: &str) -> Option<(Vec<Fd>, bool)> {
    let utm = || Fd::of("utm", Ty::DictStr).dflt(json!({}));
    let lit = |n: &'static str, l: &'static [&'static str]| Fd::of(n, Ty::Lit(l));
    let b = |n: &'static str| Fd::of(n, Ty::Bool);
    let social = || {
        vec![
            s("content").len(1, 10000),
            Fd::of(
                "account_ids",
                Ty::ListStr {
                    min: 1,
                    max: Some(10),
                },
            ),
            s("link").len(0, 2000).dflt(json!("")),
            s("hashtags").len(0, 2000).dflt(json!("")),
            Fd::of(
                "media",
                Ty::ListStr {
                    min: 0,
                    max: Some(10),
                },
            )
            .dflt(json!([])),
            Fd::of("options", Ty::Dict).dflt(json!({})),
        ]
    };
    Some(match name {
        "ChatRequest" => (
            vec![
                s("key"),
                s("session_id"),
                s("message").len(1, 1000),
                s("page_url").opt(),
                utm(),
            ],
            false,
        ),
        "VoiceTokenRequest" => (
            vec![
                s("key"),
                s("session_id"),
                b("recording_consent").dflt(json!(false)),
            ],
            false,
        ),
        "ToolRequest" => (
            vec![
                s("key"),
                s("session_id"),
                Fd::of("args", Ty::Dict).dflt(json!({})),
                s("page_url").opt(),
                utm(),
                Fd::of("voice_session_id", Ty::Uuid).opt(),
                s("voice_session_token").len(0, 200).dflt(json!("")),
            ],
            false,
        ),
        "VoiceLogRequest" => (
            vec![
                s("key"),
                s("session_id"),
                s("role").pat("^(user|assistant)$"),
                s("text").len(1, 4000),
                s("page_url").opt(),
                utm(),
            ],
            false,
        ),
        "TenantCreate" => (
            vec![
                s("name"),
                s("site_url").opt(),
                s("slug").opt(),
                s("persona").dflt(json!("")),
                s("greeting").dflt(json!("")),
                s("booking_url").opt(),
                s("lead_webhook_url").opt(),
                s("incentive").dflt(json!("")),
                Fd::of("allowed_origins", Ty::ListStr { min: 0, max: None }).dflt(json!([])),
            ],
            false,
        ),
        "TenantUpdate" => {
            let o = |f: Fd| f.opt();
            (
                vec![
                    o(s("name")),
                    o(s("site_url")),
                    o(Fd::of("allowed_origins", Ty::ListStr { min: 0, max: None })),
                    o(s("persona")),
                    o(s("greeting")),
                    o(s("cta_text")),
                    o(s("accent_color")),
                    o(s("voice")),
                    o(b("voice_enabled")),
                    o(b("phone_enabled")),
                    o(Fd::int("phone_daily_limit", 0, 100_000)),
                    o(Fd::int("voice_daily_limit", 0, 100_000)),
                    o(s("booking_url")),
                    o(s("lead_webhook_url")),
                    o(s("incentive")),
                    o(Fd::of("timezone", Ty::Tz)),
                    o(Fd::of("business_hours", Ty::Hours)),
                    o(Fd::int("slot_minutes", 5, 240)),
                    o(Fd::int("min_notice_hours", 0, 720)),
                    o(Fd::int("max_days_ahead", 1, 365)),
                    o(b("native_booking")),
                    o(s("notify_email")),
                    o(b("sms_enabled")),
                    o(s("sms_from")),
                    o(Fd::of("lead_sms_template", Ty::Template)),
                    o(s("review_url")),
                    o(Fd::int("lead_value_cents", 0, 100_000_000)),
                    o(Fd::int("sla_minutes", 0, 1440)),
                    o(Fd::int("sla_min_score", 0, 100)),
                    o(b("campaigns_enabled")),
                    o(b("weekly_digest")),
                    o(Fd::of("scoring", Ty::Scoring)),
                ],
                false,
            )
        }
        "CloneRequest" => (vec![s("name"), s("site_url").opt(), s("slug").opt()], false),
        "LeadUpdate" => (
            vec![
                lit("status", STATUSES).opt(),
                s("notes").len(0, 4000).opt(),
                Fd::int("value_cents", 0, 100_000_000).opt(),
                s("lost_reason").len(0, 300).opt(),
                Fd::of("next_action_at", Ty::Datetime).opt(),
            ],
            false,
        ),
        "AppointmentUpdate" => (
            vec![lit(
                "status",
                &["booked", "completed", "cancelled", "no_show"],
            )],
            false,
        ),
        "CrawlRequest" => (vec![Fd::int("max_pages", 1, 300).dflt(json!(40))], false),
        "IngestTextRequest" => (
            vec![
                s("label").len(1, 80).pat("^[A-Za-z0-9_.-]+$"),
                s("title").dflt(json!("")),
                s("text").len(1, 200_000),
            ],
            false,
        ),
        "CampaignCreate" => (
            vec![
                s("name").len(1, 120),
                lit("channel", &["sms", "email"]),
                s("subject").len(0, 200).dflt(json!("")),
                s("body").len(1, 600),
                Fd::int("older_than_days", 0, 3650).dflt(json!(30)),
                Fd::of("statuses", Ty::ListLit(STATUSES)).dflt(json!(["new", "contacted", "lost"])),
                Fd::int("min_score", 0, 100).dflt(json!(0)),
                Fd::of(
                    "max_recipients",
                    Ty::Int {
                        ge: Some(1),
                        le: None,
                    },
                )
                .opt(),
            ],
            false,
        ),
        "CampaignSend" => (
            vec![Fd::of(
                "expected_recipients",
                Ty::Int {
                    ge: Some(0),
                    le: None,
                },
            )],
            false,
        ),
        "MarketingConsent" => (vec![b("consent"), s("basis").len(5, 300)], false),
        "TaskCreate" => (
            vec![
                s("title").len(1, 200),
                s("notes").len(0, 2000).dflt(json!("")),
                Fd::of("due_at", Ty::Datetime).opt(),
                s("lead_id").opt(),
            ],
            false,
        ),
        "TaskUpdate" => (
            vec![
                s("title").len(0, 200).opt(),
                s("notes").len(0, 2000).opt(),
                Fd::of("due_at", Ty::Datetime).opt(),
                lit("status", &["open", "done"]).opt(),
            ],
            false,
        ),
        "EmailDraftCreate" => (
            vec![
                s("sender").len(3, 320),
                s("subject").len(0, 250).dflt(json!("")),
                s("inbound_body").len(1, 20000),
                s("reply_body").len(0, 10000).opt(),
                s("source_id").len(0, 500).dflt(json!("")),
                b("generate").dflt(json!(false)),
            ],
            false,
        ),
        "EmailDraftRevision" => (vec![s("reply_body").len(1, 10000)], false),
        "PhoneNumberCreate" => (vec![s("e164").pat(r"^\+[1-9]\d{6,14}$")], false),
        "PhoneNumberEnable" => (vec![b("enabled")], false),
        "InboundMailbox" => (
            vec![s("recipient").len(3, 320), b("enabled").dflt(json!(false))],
            false,
        ),
        "OwnerInvite" => (
            vec![
                s("email").len(0, 320),
                lit("role", &["viewer", "editor", "owner"]).dflt(json!("viewer")),
            ],
            false,
        ),
        "OwnerRecovery" => (vec![s("email").len(0, 320)], false),
        "OwnerRedeem" => (
            vec![s("token").len(20, 256), s("password").len(12, 256)],
            false,
        ),
        "OwnerLogin" => (vec![s("slug"), s("email"), s("password")], false),
        "VoiceCopyRequest" => (
            vec![
                s("recipient").len(1, 254),
                lit("channel", &["sms", "email"]),
                lit("content", &["text", "recording"]),
                Fd::of("request_id", Ty::Uuid),
                Fd::of("session_id", Ty::Uuid).opt(),
            ],
            false,
        ),
        "PhoneSmsTest" => (
            vec![
                Fd::of("acknowledgement", Ty::True),
                s("request_id").pat("^[a-f0-9-]{36}$"),
            ],
            true,
        ),
        "OwnerSocialDraft" => (social(), false),
        "OwnerSocialCompose" => {
            let mut f = social();
            f.push(s("video").len(0, 2048).opt());
            (f, false)
        }
        "OwnerSocialSchedule" => (
            vec![Fd::of(
                "scheduled_at",
                Ty::Int {
                    ge: Some(0),
                    le: None,
                },
            )],
            false,
        ),
        "OwnerOAuthCallback" => (vec![s("state").len(32, 256), s("code").len(1, 2048)], false),
        _ => return None,
    })
}

#[derive(Debug, PartialEq)]
pub enum Outcome {
    Errors(Vec<FieldErr>),
    Unsupported(&'static str),
}

fn dt(v: &Value) -> Result<Value, Result<&'static str, Outcome>> {
    static RE: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    let re = RE.get_or_init(|| {
        Regex::new(r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?(Z|[+-]\d{2}:\d{2})?$")
            .unwrap()
    });
    match v {
        Value::String(t) => {
            let Some(c) = re.captures(t) else {
                return Err(Err(Outcome::Unsupported("datetime text")));
            };
            let n = |i: usize| c.get(i).map_or(0u32, |m| m.as_str().parse().unwrap());
            let (y, mo, d, h, mi, se) = (n(1), n(2), n(3), n(4), n(5), n(6));
            let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
            let dim = [
                31,
                if leap { 29 } else { 28 },
                31,
                30,
                31,
                30,
                31,
                31,
                30,
                31,
                30,
                31,
            ];
            if !(1..=12).contains(&mo)
                || d < 1
                || d > dim[(mo - 1) as usize]
                || h > 23
                || mi > 59
                || se > 59
            {
                return Err(Err(Outcome::Unsupported("datetime range error type")));
            }
            let tz = match c.get(7).map(|m| m.as_str()) {
                None | Some("Z") | Some("+00:00") | Some("-00:00") => "Z".to_string(),
                Some(o) => o.to_string(),
            };
            if c.get(4).is_none() && c.get(7).is_some() {
                return Err(Err(Outcome::Unsupported("datetime text")));
            }
            Ok(json!(format!(
                "{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{se:02}{tz}"
            )))
        }
        Value::Number(_) => Err(Err(Outcome::Unsupported("numeric timestamp"))),
        _ => Err(Ok("datetime_type")),
    }
}

fn uuid(v: &Value) -> Result<Value, &'static str> {
    let Value::String(t) = v else {
        return Err("uuid_type");
    };
    let mut x = t.as_str();
    if let Some(r) = x.strip_prefix("urn:uuid:") {
        x = r;
    }
    if let Some(r) = x.strip_prefix('{').and_then(|r| r.strip_suffix('}')) {
        x = r;
    }
    let hex: String = if x.len() == 36 {
        let b = x.as_bytes();
        if ![8, 13, 18, 23].iter().all(|&i| b[i] == b'-') {
            return Err("uuid_parsing");
        }
        x.chars().filter(|c| *c != '-').collect()
    } else {
        x.to_string()
    };
    if hex.len() != 32 || !hex.bytes().all(|c| c.is_ascii_hexdigit()) {
        return Err("uuid_parsing");
    }
    let h = hex.to_lowercase();
    Ok(json!(format!(
        "{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    )))
}

fn weekday_hours(map: &Map<String, Value>) -> bool {
    let days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
    let re = Regex::new(r"^([01]\d|2[0-3]):[0-5]\d$").unwrap();
    for (k, windows) in map {
        if !days.contains(&k.as_str()) {
            return false;
        }
        for w in windows.as_array().unwrap() {
            let w: Vec<&str> = w
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_str().unwrap())
                .collect();
            if w.len() != 2 || !w.iter().all(|x| re.is_match(x)) || w[0] >= w[1] {
                return false;
            }
        }
    }
    true
}

/// Validate one field value; `Ok(value)` is the normalised value, `Err` pushes errors.
fn field(f: &Fd, v: &Value, errors: &mut Vec<FieldErr>) -> Result<Value, Outcome> {
    let n = f.name;
    let mut fail = |loc: String, ty: &'static str| errors.push(FieldErr { loc, ty });
    match &f.ty {
        Ty::Str { min, max, pat } => match v {
            Value::String(t) => {
                let c = t.chars().count();
                if c < *min {
                    fail(n.into(), "string_too_short");
                } else if max.is_some_and(|m| c > m) {
                    fail(n.into(), "string_too_long");
                } else if pat.is_some_and(|p| !Regex::new(p).unwrap().is_match(t)) {
                    fail(n.into(), "string_pattern_mismatch");
                } else {
                    return Ok(v.clone());
                }
            }
            _ => fail(n.into(), "string_type"),
        },
        Ty::Int { ge, le } => match parse_int(v) {
            Ok(x) if ge.is_some_and(|g| x < g as i128) => fail(n.into(), "greater_than_equal"),
            Ok(x) if le.is_some_and(|l| x > l as i128) => fail(n.into(), "less_than_equal"),
            Ok(x) if x > i64::MAX as i128 || x < i64::MIN as i128 => {
                return Err(Outcome::Unsupported("integer beyond 64 bits"))
            }
            Ok(x) => return Ok(json!(x as i64)),
            Err("int_parsing_size") => return Err(Outcome::Unsupported("huge integer text")),
            Err(t) => fail(n.into(), t),
        },
        Ty::Bool => match parse_bool(v) {
            Ok(b) => return Ok(json!(b)),
            Err(t) => fail(n.into(), t),
        },
        Ty::True => match v {
            // Literal[True] also accepts the integer 1 (pydantic compares by value)
            Value::Bool(true) => return Ok(json!(true)),
            Value::Number(x) if x.as_f64() == Some(1.0) => return Ok(json!(true)),
            _ => fail(n.into(), "literal_error"),
        },
        Ty::Lit(allowed) => match v.as_str().filter(|x| allowed.contains(x)) {
            Some(_) => return Ok(v.clone()),
            None => fail(n.into(), "literal_error"),
        },
        Ty::ListStr { min, max } => {
            if let Some(val) = list_field(n, v, errors, None, *min, *max) {
                return Ok(val);
            }
        }
        Ty::ListLit(allowed) => {
            if let Some(val) = list_field(n, v, errors, Some(allowed), 0, None) {
                return Ok(val);
            }
        }
        Ty::DictStr => match v.as_object() {
            None => fail(n.into(), "dict_type"),
            Some(m) => {
                let before = errors.len();
                for (k, x) in m {
                    if !x.is_string() {
                        errors.push(FieldErr {
                            loc: format!("{n}.{k}"),
                            ty: "string_type",
                        });
                    }
                }
                if errors.len() == before {
                    return Ok(v.clone());
                }
            }
        },
        Ty::Dict => match v {
            Value::Object(_) => return Ok(v.clone()),
            _ => fail(n.into(), "dict_type"),
        },
        Ty::Uuid => match uuid(v) {
            Ok(u) => return Ok(u),
            Err(t) => fail(n.into(), t),
        },
        Ty::Datetime => match dt(v) {
            Ok(d) => return Ok(d),
            Err(Ok(t)) => fail(n.into(), t),
            Err(Err(o)) => return Err(o),
        },
        Ty::Hours => {
            let before = errors.len();
            hours_field(n, v, errors);
            if errors.len() == before {
                return Ok(v.clone());
            }
        }
        Ty::Scoring => match v.as_object() {
            None => fail(n.into(), "dict_type"),
            Some(m) => {
                let before = errors.len();
                let mut clean = Map::new();
                for (k, x) in m {
                    match parse_int(x) {
                        Ok(i) => {
                            clean.insert(k.clone(), json!(i as i64));
                        }
                        Err("int_parsing_size") => {
                            return Err(Outcome::Unsupported("huge integer text"))
                        }
                        Err(t) => errors.push(FieldErr {
                            loc: format!("{n}.{k}"),
                            ty: t,
                        }),
                    }
                }
                if errors.len() == before {
                    match scoring::validate_overrides(&Value::Object(clean.clone())) {
                        Ok(_) => return Ok(Value::Object(clean)),
                        Err(_) => errors.push(err(n, "value_error")),
                    }
                }
            }
        },
        Ty::Tz => match v {
            Value::String(z) => {
                if owner_profile::timezone_ok(z) {
                    return Ok(v.clone());
                }
                fail(n.into(), "value_error");
            }
            _ => fail(n.into(), "string_type"),
        },
        Ty::Template => match v {
            Value::String(t) => match template_ok(t) {
                Ok(true) => return Ok(v.clone()),
                Ok(false) => fail(n.into(), "value_error"),
                Err(()) => return Err(Outcome::Unsupported("format spec or attribute access")),
            },
            _ => fail(n.into(), "string_type"),
        },
    }
    Ok(Value::Null)
}

fn list_field(
    n: &str,
    v: &Value,
    errors: &mut Vec<FieldErr>,
    literals: Option<&[&str]>,
    min: usize,
    max: Option<usize>,
) -> Option<Value> {
    let Some(items) = v.as_array() else {
        errors.push(err(n, "list_type"));
        return None;
    };
    let before = errors.len();
    for (i, x) in items.iter().enumerate() {
        let bad = match literals {
            Some(a) => (!x.as_str().is_some_and(|t| a.contains(&t))).then_some("literal_error"),
            None => (!x.is_string()).then_some("string_type"),
        };
        if let Some(t) = bad {
            errors.push(FieldErr {
                loc: format!("{n}.{i}"),
                ty: t,
            });
        }
    }
    if errors.len() > before {
        return None;
    }
    if literals.is_none() {
        if items.len() < min {
            errors.push(err(n, "too_short"));
            return None;
        }
        if max.is_some_and(|m| items.len() > m) {
            errors.push(err(n, "too_long"));
            return None;
        }
    }
    Some(v.clone())
}

fn hours_field(n: &str, v: &Value, errors: &mut Vec<FieldErr>) {
    let Some(days) = v.as_object() else {
        errors.push(err(n, "dict_type"));
        return;
    };
    let before = errors.len();
    for (day, windows) in days {
        let Some(list) = windows.as_array() else {
            errors.push(FieldErr {
                loc: format!("{n}.{day}"),
                ty: "list_type",
            });
            continue;
        };
        for (i, w) in list.iter().enumerate() {
            let Some(pair) = w.as_array() else {
                errors.push(FieldErr {
                    loc: format!("{n}.{day}.{i}"),
                    ty: "list_type",
                });
                continue;
            };
            for (j, x) in pair.iter().enumerate() {
                if !x.is_string() {
                    errors.push(FieldErr {
                        loc: format!("{n}.{day}.{i}.{j}"),
                        ty: "string_type",
                    });
                }
            }
        }
    }
    if errors.len() == before && !weekday_hours(days) {
        errors.push(err(n, "value_error"));
    }
}

/// `value.format(first="A", name="A", business="A")` succeeds. `Err(())`: attribute/index access or a format spec (declined).
fn template_ok(t: &str) -> Result<bool, ()> {
    use crate::campaigns::{tokenize, Tok};
    let Ok(toks) = tokenize(t) else {
        return Ok(false);
    };
    for tok in toks {
        if let Tok::Field(f) = tok {
            if f.name.contains(['.', '[']) {
                return Err(());
            }
            if !["first", "name", "business"].contains(&f.name.as_str()) {
                return Ok(false);
            }
            match f.conversion {
                None | Some('s' | 'r' | 'a') => {}
                Some(_) => return Ok(false),
            }
            if !f.spec.is_empty() {
                return Err(());
            }
        }
    }
    Ok(true)
}

/// `Model.model_validate(body).model_dump(mode="json")`.
pub fn validate(name: &str, body: &Value) -> Result<Value, Outcome> {
    let (fields, forbid) = model(name).expect("known model");
    let Some(map) = body.as_object() else {
        return Err(Outcome::Errors(vec![err("", "model_type")]));
    };
    let mut errors = Vec::new();
    let mut out = Map::new();
    for f in &fields {
        match map.get(f.name) {
            None => match &f.default {
                Some(d) => {
                    out.insert(f.name.into(), d.clone());
                }
                None => errors.push(err(f.name, "missing")),
            },
            Some(Value::Null) if f.nullable => {
                out.insert(f.name.into(), Value::Null);
            }
            Some(v) => {
                let before = errors.len();
                let val = field(f, v, &mut errors)?;
                if errors.len() == before {
                    out.insert(f.name.into(), val);
                }
            }
        }
    }
    if forbid {
        let known: Vec<&str> = fields.iter().map(|f| f.name).collect();
        errors.extend(crate::pydantic::extras(map, &known));
    }
    if errors.is_empty() {
        Ok(Value::Object(out))
    } else {
        Err(Outcome::Errors(errors))
    }
}

// ---- small helpers from main.py ----------------------------------------------------------------------------------------

pub fn origin_of(url: &str) -> Result<String, Fail> {
    let p = urlsplit(url, "")?;
    Ok(format!("{}://{}", p.scheme, p.netloc).to_lowercase())
}

/// The allowed-origin decision in `_tenant_for`: `Err((403, "Origin not allowed"))` when refused.
pub fn origin_gate(
    allowed: &[&str],
    origin: Option<&str>,
    public_base_url: &str,
) -> Result<(), (u16, &'static str)> {
    if allowed.is_empty() {
        return Ok(());
    }
    let Some(origin) = origin.filter(|o| !o.is_empty()) else {
        return Ok(());
    };
    let mut permitted: Vec<String> = allowed
        .iter()
        .map(|o| o.trim_end_matches('/').to_lowercase())
        .collect();
    permitted.push(origin_of(public_base_url).unwrap_or_default());
    if permitted.contains(&origin.trim_end_matches('/').to_lowercase()) {
        Ok(())
    } else {
        Err((403, "Origin not allowed"))
    }
}

/// `_rate_limit`: which limiter is asked, in order, and the refusal. `ip_check`/`session_check` are the limiters.
pub fn rate_limit(
    client_ip: Option<&str>,
    session_id: Option<&str>,
    ip_check: &mut dyn FnMut(&str) -> bool,
    session_check: &mut dyn FnMut(&str) -> bool,
) -> Result<(), (u16, &'static str)> {
    if !ip_check(client_ip.unwrap_or("unknown")) {
        return Err((429, "Too many requests, please slow down"));
    }
    if let Some(s) = session_id.filter(|s| !s.is_empty()) {
        if !session_check(s) {
            return Err((429, "Session limit reached"));
        }
    }
    Ok(())
}

/// `f"${cents / 100:,.0f}"`: whole dollars, banker's rounding on the exact binary value, thousands separators.
pub fn money(cents: i64) -> String {
    let dollars = cents as f64 / 100.0;
    let rounded = format!("{:.0}", dollars.abs());
    let mut grouped = String::new();
    for (i, c) in rounded.chars().enumerate() {
        if i > 0 && (rounded.len() - i) % 3 == 0 {
            grouped.push(',');
        }
        grouped.push(c);
    }
    // Python prints the sign after the dollar sign, and keeps it when the value rounds to zero ("$-0")
    format!("${}{}", if dollars < 0.0 { "-" } else { "" }, grouped)
}

pub fn twiml(text: &str) -> String {
    let mut body = String::from(r#"<?xml version="1.0" encoding="UTF-8"?><Response>"#);
    if !text.is_empty() {
        let t: String = text.chars().take(1500).collect();
        body.push_str(&format!(
            "<Message>{}</Message>",
            t.replace('&', "&amp;")
                .replace('<', "&lt;")
                .replace('>', "&gt;")
        ));
    }
    body.push_str("</Response>");
    body
}

pub fn with_snippet(base: &str, tenant: &Value) -> Value {
    let mut t = tenant.as_object().cloned().unwrap_or_default();
    let g = |k: &str| tenant[k].as_str().unwrap_or("").to_string();
    t.insert(
        "embed_snippet".into(),
        json!(format!(
            r#"<script src="{base}/widget.js" data-key="{}" defer></script>"#,
            g("public_key")
        )),
    );
    t.insert(
        "demo_url".into(),
        json!(format!("{base}/demo/{}?presenter=1", g("slug"))),
    );
    t.insert(
        "report_url".into(),
        json!(format!("{base}/report/{}", g("report_token"))),
    );
    t.insert(
        "sms_webhook_url".into(),
        json!(format!("{base}/api/v1/sms/{}", g("public_key"))),
    );
    t.insert(
        "calendar_url".into(),
        if crate::pyval::truthy(tenant.get("calendar_token")) {
            json!(format!(
                "{base}/api/v1/calendar/{}.ics",
                g("calendar_token")
            ))
        } else {
            Value::Null
        },
    );
    Value::Object(t)
}

pub fn campaign_view(c: &Value) -> Result<Value, &'static str> {
    let mut v = c.as_object().cloned().unwrap_or_default();
    if let Some(Value::String(text)) = v.get("filters") {
        let parsed: Value = serde_json::from_str(text).map_err(|_| "invalid JSON")?;
        v.insert("filters".into(), parsed);
    }
    Ok(Value::Object(v))
}

/// Headers of a private audio download.
pub fn private_audio_headers(filename: &str, mime: &str) -> Vec<(String, String)> {
    let h = |k: &str, v: &str| (k.to_string(), v.to_string());
    vec![
        h("content-type", mime),
        h("cache-control", "private, no-store"),
        h("x-content-type-options", "nosniff"),
        h("referrer-policy", "no-referrer"),
        h("x-robots-tag", "noindex, nofollow, noarchive"),
        h(
            "content-disposition",
            &format!("inline; filename=\"{filename}\""),
        ),
    ]
}

#[allow(dead_code)]
fn _strip(s: &str) -> &str {
    py_strip(s)
}
