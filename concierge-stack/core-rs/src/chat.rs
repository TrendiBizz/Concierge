//! Port of `chat.run_turn`: one conversation turn shared by web chat, SMS and email. Every effect (storage, retrieval, the
//! model, tools, the owner notice) is an `Env` call, so the exact order and content can be compared with the Python original.
//! Nothing here sends a message: the owner notice is only *queued* through `Env`, and only outside dry runs.
use crate::convo::clean_utm;
use crate::rag::build_system_prompt;
use crate::tools::chat_tools;
use crate::{guard, py_strip, pyjson, pyval::truthy};
use chrono::{DateTime, Utc};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

pub const MAX_TOOL_ROUNDS: usize = 4;
pub const GENERIC_FAILURE: &str = "Sorry, I had trouble with that. Could you rephrase, or leave your phone number or email so the team can follow up?";

pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: Option<String>,
}

pub struct Completion {
    pub content: Option<String>,
    pub tool_calls: Vec<ToolCall>,
}

pub trait Env {
    fn get_or_create(
        &mut self,
        session_id: &str,
        channel: &str,
        page_url: Option<&str>,
        utm: Option<&Map<String, Value>>,
    ) -> String;
    fn capture_enquiry(&mut self, conversation_id: &str, message: &str);
    fn history(&mut self, conversation_id: &str) -> Vec<(String, String)>;
    fn save_message(
        &mut self,
        conversation_id: &str,
        role: &str,
        content: &str,
        flag: Option<&str>,
    );
    fn retrieve(&mut self, message: &str) -> Vec<Value>;
    fn complete(&mut self, messages: &[Value], tools: Option<&[Value]>) -> Completion;
    fn run_tool(&mut self, name: &str, args: Value, ctx: &mut Map<String, Value>) -> Value;
    fn dialogue(&mut self, conversation_id: &str) -> Vec<(String, String)>;
    fn first_lead(&mut self, conversation_id: &str) -> Option<String>;
    fn queue_owner_notice(
        &mut self,
        subject: &str,
        body: &str,
        dedupe_key: &str,
        lead_id: Option<&str>,
    );
}

pub struct Turn<'a> {
    pub tenant: &'a Value,
    pub session_id: &'a str,
    pub channel: &'a str,
    pub message: &'a str,
    pub page_url: Option<&'a str>,
    pub utm: Option<&'a Map<String, Value>>,
    pub sender_phone: Option<&'a str>,
    pub sender_email: Option<&'a str>,
    pub dry_run: bool,
    pub now: DateTime<Utc>,
}

/// `Err` only when a value needs a Python repr this port does not reproduce (floats in tool results or UTM values).
fn run_llm(
    env: &mut dyn Env,
    messages: &mut Vec<Value>,
    tenant: &Value,
    ctx: &mut Map<String, Value>,
) -> Result<String, &'static str> {
    let tools = chat_tools(tenant);
    for _ in 0..MAX_TOOL_ROUNDS {
        let msg = env.complete(messages, Some(&tools));
        if msg.tool_calls.is_empty() {
            return Ok(py_strip(msg.content.as_deref().unwrap_or("")).to_string());
        }
        messages.push(json!({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": msg.tool_calls.iter().map(|tc| json!({
                "id": tc.id, "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            })).collect::<Vec<_>>(),
        }));
        for tc in &msg.tool_calls {
            let raw = match tc.arguments.as_deref() {
                Some(a) if !a.is_empty() => a,
                _ => "{}",
            };
            let args: Value = serde_json::from_str(raw).unwrap_or_else(|_| json!({}));
            let result = env.run_tool(&tc.name, args, ctx);
            let content = pyjson::dumps(&result).ok_or("tool result needs a Python float repr")?;
            messages.push(json!({"role": "tool", "tool_call_id": tc.id, "content": content}));
        }
    }
    Ok(String::new())
}

pub fn run_turn(env: &mut dyn Env, t: &Turn) -> Result<Value, &'static str> {
    let tenant = t.tenant;
    let conversation_id = env.get_or_create(t.session_id, t.channel, t.page_url, t.utm);
    let utm_clean = match t.utm {
        None => Vec::new(),
        Some(u) => clean_utm(u).ok_or("UTM value needs a Python repr")?,
    };
    let mut ctx = Map::new();
    ctx.insert("conversation_id".into(), json!(conversation_id));
    ctx.insert("channel".into(), json!(t.channel));
    ctx.insert("page_url".into(), json!(t.page_url));
    ctx.insert(
        "utm".into(),
        Value::Object(utm_clean.into_iter().map(|(k, v)| (k, json!(v))).collect()),
    );
    ctx.insert("sender_phone".into(), json!(t.sender_phone));
    ctx.insert("sms_inbound".into(), json!(t.channel == "sms"));
    ctx.insert("dry_run".into(), json!(t.dry_run));

    if t.channel == "chat" && !t.dry_run {
        env.capture_enquiry(&conversation_id, t.message);
    }
    let history = env.history(&conversation_id);
    env.save_message(&conversation_id, "user", t.message, None);

    let hits = env.retrieve(t.message);
    let prompt_channel = match t.channel {
        "voice" | "phone" => "voice",
        "sms" => "sms",
        "email" => "email",
        _ => "chat",
    };
    let mut messages: Vec<Value> = vec![
        json!({"role": "system", "content": build_system_prompt(tenant, Some(&hits), prompt_channel, t.now)}),
    ];
    if let Some(email) = t.sender_email.filter(|e| !e.is_empty()) {
        messages.push(json!({"role": "system", "content": format!("Reply address supplied by authenticated email ingress: {email}")}));
    }
    for (role, content) in history {
        messages.push(json!({"role": role, "content": content}));
    }
    messages.push(json!({"role": "user", "content": t.message}));

    let mut reply = run_llm(env, &mut messages, tenant, &mut ctx)?;

    let mut flag: Option<&str> = None;
    let mut evidence: Vec<String> = hits
        .iter()
        .map(|h| h["content"].as_str().unwrap_or("").to_string())
        .collect();
    if let Some(Value::Array(results)) = ctx.get("tool_results") {
        evidence.extend(results.iter().map(|r| r.as_str().unwrap_or("").to_string()));
    }
    for key in ["persona", "incentive"] {
        evidence.push(if truthy(tenant.get(key)) {
            tenant[key].as_str().unwrap_or("").to_string()
        } else {
            String::new()
        });
    }
    let evidence = evidence.join("\n");
    if !reply.is_empty() && !guard::unknown_amounts(&reply, &evidence).is_empty() {
        flag = Some("quote_guard");
        let mut retry = messages.clone();
        retry.push(json!({"role": "assistant", "content": reply}));
        retry.push(json!({"role": "system", "content": guard::CORRECTION}));
        let second = env.complete(&retry, None);
        reply = py_strip(second.content.as_deref().unwrap_or("")).to_string();
        if reply.is_empty() || !guard::unknown_amounts(&reply, &evidence).is_empty() {
            reply = guard::FALLBACK.to_string();
        }
    }
    if reply.is_empty() {
        reply = GENERIC_FAILURE.to_string();
    }

    env.save_message(&conversation_id, "assistant", &reply, flag);
    if matches!(t.channel, "chat" | "sms" | "email") && !t.dry_run {
        let rows = env.dialogue(&conversation_id);
        let dialogue = rows
            .iter()
            .map(|(role, content)| {
                format!(
                    "{}: {}",
                    if role == "user" {
                        "Enquirer"
                    } else {
                        "Concierge"
                    },
                    content
                )
            })
            .collect::<Vec<_>>()
            .join("\n\n");
        let lead = env.first_lead(&conversation_id);
        let key: String =
            Sha256::digest(format!("{conversation_id}{}{reply}", t.message).as_bytes())
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect();
        let title = match t.channel {
            "chat" => "Chat",
            "sms" => "Sms",
            _ => "Email",
        };
        let tenant_id = tenant["id"].as_str().unwrap_or("");
        env.queue_owner_notice(
            &format!(
                "{title} conversation for {}",
                tenant["name"].as_str().unwrap_or("")
            ),
            &dialogue,
            &format!("dialogue:{tenant_id}:{key}"),
            lead.as_deref(),
        );
    }
    Ok(json!({
        "reply": reply,
        "lead_captured": truthy(ctx.get("lead_captured")),
        "booking_url": ctx.get("booking_url").cloned().unwrap_or(Value::Null),
        "appointment": ctx.get("appointment_text").cloned().unwrap_or(Value::Null),
        "guard_triggered": flag == Some("quote_guard"),
        "tool_calls": ctx.get("tool_calls").cloned().unwrap_or_else(|| json!([])),
    }))
}
