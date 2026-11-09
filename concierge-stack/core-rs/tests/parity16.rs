//! Batch 16: one conversation turn against the live `chat.run_turn` with a scripted model, scripted tools and a recording environment.
use chrono::DateTime;
use concierge_core::chat::{run_turn, Completion, Env, ToolCall, Turn};
use concierge_core::tools::chat_tools;
use serde_json::{json, Map, Value};

struct Fake<'a> {
    c: &'a Value,
    effects: Vec<Value>,
    llm_i: usize,
    tool_i: usize,
}

impl Env for Fake<'_> {
    fn get_or_create(
        &mut self,
        session: &str,
        channel: &str,
        page: Option<&str>,
        utm: Option<&Map<String, Value>>,
    ) -> String {
        self.effects.push(json!([
            "get_or_create",
            [self.c["tenant"]["id"], session, channel, page, utm]
        ]));
        "conv-1".into()
    }
    fn capture_enquiry(&mut self, cid: &str, message: &str) {
        self.effects.push(json!(["capture", [self.c["tenant"]["id"], "chat", cid, message, {"conversation_id": cid}]]));
    }
    fn history(&mut self, cid: &str) -> Vec<(String, String)> {
        self.effects.push(json!(["history", [cid]]));
        pairs(&self.c["history"])
    }
    fn save_message(&mut self, cid: &str, role: &str, content: &str, flag: Option<&str>) {
        self.effects
            .push(json!(["save", [cid, role, content, flag]]));
    }
    fn retrieve(&mut self, message: &str) -> Vec<Value> {
        self.effects
            .push(json!(["retrieve", [self.c["tenant"]["id"], message]]));
        self.c["hits"].as_array().unwrap().clone()
    }
    fn complete(&mut self, messages: &[Value], tools: Option<&[Value]>) -> Completion {
        self.effects.push(json!(["llm", [messages, tools]]));
        let rounds = self.c["rounds"].as_array().unwrap();
        let r = if self.llm_i < rounds.len() {
            &rounds[self.llm_i]
        } else {
            &self.c["retry"]
        };
        self.llm_i += 1;
        Completion {
            content: r["content"].as_str().map(String::from),
            tool_calls: r["calls"]
                .as_array()
                .unwrap()
                .iter()
                .map(|t| ToolCall {
                    id: t["id"].as_str().unwrap().into(),
                    name: t["name"].as_str().unwrap().into(),
                    arguments: t["arguments"].as_str().map(String::from),
                })
                .collect(),
        }
    }
    fn run_tool(&mut self, name: &str, args: Value, ctx: &mut Map<String, Value>) -> Value {
        let s = &self.c["tool_script"][self.tool_i];
        self.tool_i += 1;
        self.effects.push(json!([
            "tool",
            [
                name,
                args,
                Value::Object(ctx.clone()),
                s["result"],
                s["update"]
            ]
        ]));
        for (k, v) in s["update"].as_object().unwrap() {
            ctx.insert(k.clone(), v.clone());
        }
        s["result"].clone()
    }
    fn dialogue(&mut self, cid: &str) -> Vec<(String, String)> {
        self.effects.push(json!(["dialogue", [cid]]));
        pairs(&self.c["dialogue"])
    }
    fn first_lead(&mut self, cid: &str) -> Option<String> {
        self.effects
            .push(json!(["lead", [self.c["tenant"]["id"], cid]]));
        self.c["lead"].as_str().map(String::from)
    }
    fn queue_owner_notice(&mut self, subject: &str, body: &str, dedupe: &str, lead: Option<&str>) {
        self.effects.push(json!([
            "owner",
            [self.c["tenant"]["id"], subject, body, dedupe, lead]
        ]));
    }
}

fn pairs(v: &Value) -> Vec<(String, String)> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|r| {
            (
                r["role"].as_str().unwrap().into(),
                r["content"].as_str().unwrap().into(),
            )
        })
        .collect()
}

#[test]
fn conversation_turns_match_python() {
    let all: Vec<Value> = serde_json::from_str(include_str!("../parity/vectors16.json")).unwrap();
    let (mut guarded, mut tooled, mut notified) = (0, 0, 0);
    for c in &all {
        let a = &c["args"];
        let mut env = Fake {
            c,
            effects: vec![],
            llm_i: 0,
            tool_i: 0,
        };
        let turn = Turn {
            tenant: &c["tenant"],
            session_id: a["session_id"].as_str().unwrap(),
            channel: c["channel"].as_str().unwrap(),
            message: a["message"].as_str().unwrap(),
            page_url: a["page_url"].as_str(),
            utm: a["utm"].as_object(),
            sender_phone: a["sender_phone"].as_str(),
            sender_email: a["sender_email"].as_str(),
            dry_run: a["dry_run"].as_bool().unwrap(),
            now: DateTime::from_timestamp(c["now"].as_i64().unwrap(), 0).unwrap(),
        };
        let got = run_turn(&mut env, &turn).unwrap_or_else(|e| panic!("{e} for {c}"));
        assert_eq!(got, c["out"], "{}", a["message"]);
        let want = c["effects"].as_array().unwrap();
        assert_eq!(env.effects.len(), want.len(), "{}", a["message"]);
        for (i, (g, w)) in env.effects.iter().zip(want).enumerate() {
            assert_eq!(g, w, "effect {i} differs for {}", a["message"]);
        }
        guarded += got["guard_triggered"].as_bool().unwrap() as i32;
        tooled += want.iter().any(|e| e[0] == "tool") as i32;
        notified += want.iter().any(|e| e[0] == "owner") as i32;
        // the tool list the model sees is the tenant's own
        let tools = chat_tools(&c["tenant"]);
        let first_llm = want.iter().find(|e| e[0] == "llm").unwrap();
        assert_eq!(json!(tools), first_llm[1][1]);
    }
    assert!(
        guarded > 40 && tooled > 80 && notified > 80,
        "{guarded} {tooled} {notified}"
    );
}
