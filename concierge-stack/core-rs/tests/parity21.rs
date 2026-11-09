//! Batch 21: `booking.availability` and `booking.book` against the live module with a fixed clock, fake database and fake calendar.
use chrono::{DateTime, Utc};
use concierge_core::booking::{self, iso, Env};
use serde_json::{json, Map, Value};

type Range = (DateTime<Utc>, DateTime<Utc>);

fn ranges(v: &Value) -> Vec<Range> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|p| {
            (
                DateTime::parse_from_rfc3339(p[0].as_str().unwrap())
                    .unwrap()
                    .to_utc(),
                DateTime::parse_from_rfc3339(p[1].as_str().unwrap())
                    .unwrap()
                    .to_utc(),
            )
        })
        .collect()
}

struct Fake<'a> {
    c: &'a Value,
    fx: Vec<Value>,
}

impl Env for Fake<'_> {
    fn now(&mut self) -> DateTime<Utc> {
        DateTime::from_timestamp(self.c["now"].as_i64().unwrap(), 0).unwrap()
    }
    fn booked(&mut self, tid: &str, s: DateTime<Utc>, e: DateTime<Utc>, txn: bool) -> Vec<Range> {
        if txn {
            self.fx
                .push(json!(["booked", [tid, iso(s), iso(e), "txn"]]));
        } else {
            self.fx.push(json!(["booked", [tid, iso(s), iso(e)]]));
        }
        let mut r = ranges(&self.c["booked"]);
        if txn && self.c["taken"] == true {
            r.push((
                DateTime::from_timestamp(946684800, 0).unwrap(),
                DateTime::from_timestamp(4102444800, 0).unwrap(),
            ));
        }
        r
    }
    fn busy(&mut self, tid: &str, s: DateTime<Utc>, e: DateTime<Utc>) -> Vec<Range> {
        self.fx.push(json!(["busy", [tid, iso(s), iso(e)]]));
        ranges(&self.c["busy"])
    }
    fn previous_booking(&mut self, tid: &str, cid: &str, start: DateTime<Utc>) -> Option<Value> {
        self.fx.push(json!(["previous", [tid, cid, iso(start)]]));
        let p = &self.c["previous"];
        (!p.is_null()).then(|| {
            let mut m = p.as_object().unwrap().clone();
            m.insert("starts_at".into(), json!(start.to_rfc3339()));
            Value::Object(m)
        })
    }
    fn pending(&mut self, cid: &str) -> Value {
        self.fx.push(json!(["get_pending", [cid]]));
        self.c["pending"].clone()
    }
    fn set_pending(&mut self, cid: &str, v: Value) {
        self.fx.push(json!(["set_pending", [cid, v]]));
    }
    fn lock_tenant(&mut self, tid: &str) {
        self.fx.push(json!(["lock", [tid]]));
    }
    fn existing_lead(&mut self, tid: &str, cid: &str) -> Option<Value> {
        self.fx.push(json!(["select_lead", [tid, cid]]));
        (!self.c["existing_lead"].is_null()).then(|| self.c["existing_lead"].clone())
    }
    fn insert_lead(
        &mut self,
        tid: &str,
        cid: Option<&str>,
        name: &str,
        email: &str,
        phone: &str,
        msg: &str,
        ch: &str,
        page: &Value,
        utm: &str,
        hook: &str,
        consent: bool,
    ) -> Value {
        self.fx.push(json!([
            "insert_lead",
            [tid, cid, name, email, phone, msg, ch, page, utm, hook, consent]
        ]));
        json!({"id": "lead-1"})
    }
    fn insert_appointment(
        &mut self,
        tid: &str,
        lead: &Value,
        cid: Option<&str>,
        s: DateTime<Utc>,
        e: DateTime<Utc>,
        name: &str,
        phone: &str,
        email: &str,
        notes: &str,
        consent: bool,
    ) -> Value {
        self.fx.push(json!([
            "insert_appointment",
            [
                tid,
                lead,
                cid,
                iso(s),
                iso(e),
                name,
                phone,
                email,
                notes,
                consent
            ]
        ]));
        json!({"id": "appt-1"})
    }
    fn sync_one(&mut self, id: &Value) {
        self.fx.push(json!(["sync_one", [id]]));
    }
    fn refetch(&mut self, tid: &str, id: &Value) -> Value {
        self.fx.push(json!(["refetch", [tid, id]]));
        let starts = if self.c["start_utc"].is_null() {
            "2026-01-01T00:00:00+00:00".to_string()
        } else {
            self.c["start_utc"].as_str().unwrap().to_string()
        };
        let mut m = self.c["refetched"].as_object().unwrap().clone();
        m.insert("id".into(), id.clone());
        m.insert("starts_at".into(), json!(starts));
        Value::Object(m)
    }
    fn notify_synced(&mut self, id: &Value) {
        self.fx.push(json!(["notify_synced", [id]]));
    }
}

#[test]
fn availability_matches_python() {
    let all = serde_json::from_str::<Value>(include_str!("../parity/vectors21.json")).unwrap();
    let (mut slots, mut empty, mut declined) = (0, 0, 0);
    for c in all["availability"].as_array().unwrap() {
        let mut env = Fake { c, fx: vec![] };
        let got = match booking::availability(&mut env, &c["tenant"], c["date"].as_str()) {
            Ok(v) => v,
            Err(_) => {
                declined += 1;
                continue;
            }
        };
        assert_eq!(got, c["out"], "{c}");
        assert_eq!(Value::Array(env.fx), c["effects"], "{c}");
        if got["slots"].as_array().is_some_and(|s| !s.is_empty()) {
            slots += 1;
        } else if got["next_available_dates"].is_array() {
            empty += 1;
        }
    }
    assert!(
        slots > 50 && empty > 50 && declined < 20,
        "{slots} {empty} {declined}"
    );
}

#[test]
fn booking_flow_matches_python() {
    let all = serde_json::from_str::<Value>(include_str!("../parity/vectors21.json")).unwrap();
    let (mut booked, mut needs, mut dup, mut declined) = (0, 0, 0, 0);
    for c in all["book"].as_array().unwrap() {
        if c["out"].get("raises").is_some() {
            continue;
        }
        let mut env = Fake { c, fx: vec![] };
        let mut ctx = c["ctx0"].as_object().unwrap().clone();
        let got = booking::book(&mut env, &c["tenant"], &c["args"], &mut ctx, "1");
        let Ok(got) = got else {
            declined += 1;
            continue;
        };
        assert_eq!(json!({"ok": got}), c["out"], "{}", c["args"]);
        assert_eq!(Value::Array(env.fx.clone()), c["effects"], "{}", c["args"]);
        assert_eq!(
            Value::Object(Map::from_iter(ctx)),
            c["ctx"],
            "{}",
            c["args"]
        );
        booked += (got["booking_status"].is_string() && got["duplicate"] == false) as i32;
        needs += (got["needs_confirmation"] == true) as i32;
        dup += (got["duplicate"] == true) as i32;
    }
    assert!(
        booked >= 40 && needs > 100 && declined < 40,
        "{booked} {needs} {dup} {declined}"
    );
}
