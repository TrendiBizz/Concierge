//! Port of the async halves of `booking.py`: the availability search and the enforced read-back, duplicate-safe, race-safe
//! booking flow. The database and calendar provider are `Env` calls so their order and content can be compared with Python.
//! The assistant never invents times: only slots computed here (business hours, notice, existing bookings and the connected
//! calendar's busy periods) are offered, and a booking is created only on a second, confirmed call for the same time and name.
use crate::booking_text::{booking_result, Appointment};
use crate::contact::{is_email, normalize_phone};
use crate::py_strip;
use crate::pyval::{str_or_empty, truthy};
use crate::schedule::{day_slots, fmt_local, local_to_utc, BookingTenant};
use chrono::{DateTime, Duration, NaiveDate, NaiveDateTime, NaiveTime, Utc};
use chrono_tz::Tz;
use regex::Regex;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::sync::OnceLock;

type Range = (DateTime<Utc>, DateTime<Utc>);

#[derive(Debug, PartialEq)]
pub struct Unsupported(pub &'static str);

pub fn iso(d: DateTime<Utc>) -> String {
    d.format("%Y-%m-%dT%H:%M:%S+00:00").to_string()
}

pub trait Env {
    fn now(&mut self) -> DateTime<Utc>;
    fn booked(
        &mut self,
        tenant_id: &str,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
        in_txn: bool,
    ) -> Vec<Range>;
    fn busy(&mut self, tenant_id: &str, start: DateTime<Utc>, end: DateTime<Utc>) -> Vec<Range>;
    fn previous_booking(
        &mut self,
        tenant_id: &str,
        conversation_id: &str,
        start: DateTime<Utc>,
    ) -> Option<Value>;
    fn pending(&mut self, conversation_id: &str) -> Value;
    fn set_pending(&mut self, conversation_id: &str, value: Value);
    fn lock_tenant(&mut self, tenant_id: &str);
    fn existing_lead(&mut self, tenant_id: &str, conversation_id: &str) -> Option<Value>;
    #[allow(clippy::too_many_arguments)]
    fn insert_lead(
        &mut self,
        tenant_id: &str,
        conversation_id: Option<&str>,
        name: &str,
        email: &str,
        phone: &str,
        message: &str,
        channel: &str,
        page_url: &Value,
        utm_json: &str,
        webhook_status: &str,
        consent: bool,
    ) -> Value;
    #[allow(clippy::too_many_arguments)]
    fn insert_appointment(
        &mut self,
        tenant_id: &str,
        lead_id: &Value,
        conversation_id: Option<&str>,
        start: DateTime<Utc>,
        end: DateTime<Utc>,
        name: &str,
        phone: &str,
        email: &str,
        notes: &str,
        consent: bool,
    ) -> Value;
    fn sync_one(&mut self, appointment_id: &Value);
    fn refetch(&mut self, tenant_id: &str, appointment_id: &Value) -> Value;
    fn notify_synced(&mut self, appointment_id: &Value);
}

fn tenant_tz(tenant: &Value) -> Tz {
    tenant["timezone"]
        .as_str()
        .unwrap_or("UTC")
        .parse()
        .unwrap_or(chrono_tz::UTC)
}

fn booking_tenant(tenant: &Value) -> BookingTenant {
    let mut hours: BTreeMap<String, Vec<(String, String)>> = BTreeMap::new();
    if let Some(m) = tenant["business_hours"].as_object() {
        for (day, w) in m {
            let v = w
                .as_array()
                .map(|a| {
                    a.iter()
                        .map(|p| {
                            (
                                p[0].as_str().unwrap_or("").to_string(),
                                p[1].as_str().unwrap_or("").to_string(),
                            )
                        })
                        .collect()
                })
                .unwrap_or_default();
            hours.insert(day.clone(), v);
        }
    }
    BookingTenant {
        timezone: tenant_tz(tenant),
        slot_minutes: tenant["slot_minutes"].as_i64().unwrap_or(30),
        min_notice_hours: tenant["min_notice_hours"].as_i64().unwrap_or(0),
        business_hours: hours,
    }
}

fn local_midnight(tz: Tz, day: NaiveDate) -> Result<DateTime<Utc>, Unsupported> {
    local_to_utc(tz, day.and_time(NaiveTime::MIN)).ok_or(Unsupported("midnight inside a DST gap"))
}

/// `_slots_on`: free slot starts (UTC) for one local day.
pub fn slots_on(
    env: &mut dyn Env,
    tenant: &Value,
    day: NaiveDate,
    in_txn: bool,
) -> Result<Vec<DateTime<Utc>>, Unsupported> {
    let tz = tenant_tz(tenant);
    let tid = tenant["id"].as_str().unwrap_or("");
    let start = local_midnight(tz, day)?;
    let end = local_midnight(tz, day + Duration::days(1))?;
    let mut booked = env.booked(tid, start, end, in_txn);
    booked.extend(env.busy(tid, start, end));
    let now = env.now();
    day_slots(&booking_tenant(tenant), day, now, &booked)
        .map_err(|_| Unsupported("invalid business hours"))
}

fn local_hm(tz: Tz, d: DateTime<Utc>) -> String {
    d.with_timezone(&tz).format("%H:%M").to_string()
}

/// `date.fromisoformat`: `Ok(None)` is Python's ValueError; forms only Python 3.11+ accepts are declined.
fn parse_day(text: &str) -> Result<Option<NaiveDate>, Unsupported> {
    static FORMS: OnceLock<[Regex; 3]> = OnceLock::new();
    let forms = FORMS.get_or_init(|| {
        [
            Regex::new(r"^([0-9]{4})-?([0-9]{2})-?([0-9]{2})$").unwrap(),
            Regex::new(r"^([0-9]{4})-W([0-9]{2})(?:-([0-9]))?$").unwrap(),
            Regex::new(r"^([0-9]{4})W([0-9]{2})([0-9])?$").unwrap(),
        ]
    });
    // calendar dates: "YYYY-MM-DD" and "YYYYMMDD" (a mixed separator form is not valid)
    if let Some(c) = forms[0].captures(text) {
        let compact = !text.contains('-');
        let dashed = text.matches('-').count() == 2;
        if !(compact || dashed) {
            return Ok(None);
        }
        let n = |i: usize| c[i].parse::<u32>().unwrap();
        return Ok(NaiveDate::from_ymd_opt(n(1) as i32, n(2), n(3)));
    }
    // ISO week dates: "YYYY-Www[-D]" and "YYYYWww[D]"
    for f in &forms[1..] {
        if let Some(c) = f.captures(text) {
            let y = c[1].parse::<i32>().unwrap();
            let w = c[2].parse::<u32>().unwrap();
            let d = c.get(3).map_or(1, |m| m.as_str().parse::<u32>().unwrap());
            let wd = match d {
                1 => chrono::Weekday::Mon,
                2 => chrono::Weekday::Tue,
                3 => chrono::Weekday::Wed,
                4 => chrono::Weekday::Thu,
                5 => chrono::Weekday::Fri,
                6 => chrono::Weekday::Sat,
                7 => chrono::Weekday::Sun,
                _ => return Ok(None),
            };
            return Ok(NaiveDate::from_isoywd_opt(y, w, wd));
        }
    }
    if !text.is_ascii() && text.chars().any(|c| c.is_numeric()) {
        return Err(Unsupported("non-ASCII digits in a date"));
    }
    Ok(None)
}

pub fn availability(
    env: &mut dyn Env,
    tenant: &Value,
    date_str: Option<&str>,
) -> Result<Value, Unsupported> {
    let tz = tenant_tz(tenant);
    let day = match parse_day(py_strip(date_str.unwrap_or("")))? {
        Some(d) => d,
        None => return Ok(json!({"ok": false, "error": "date must be YYYY-MM-DD"})),
    };
    let today = env.now().with_timezone(&tz).date_naive();
    let last = today + Duration::days(tenant["max_days_ahead"].as_i64().unwrap_or(0));
    if day < today || day > last {
        return Ok(
            json!({"ok": false, "error": format!("Bookings are open from {today} to {last}.")}),
        );
    }
    let slots = slots_on(env, tenant, day, false)?;
    let weekday = day.format("%A").to_string();
    if !slots.is_empty() {
        return Ok(json!({
            "ok": true, "date": day.to_string(), "weekday": weekday, "timezone": tenant["timezone"],
            "slots": slots.iter().take(12).map(|s| local_hm(tz, *s)).collect::<Vec<_>>(),
            "slot_minutes": tenant["slot_minutes"],
        }));
    }
    let mut upcoming = Vec::new();
    let mut probe = day + Duration::days(1);
    while probe <= last && upcoming.len() < 3 && (probe - day).num_days() <= 14 {
        let found = slots_on(env, tenant, probe, false)?;
        if let Some(first) = found.first() {
            upcoming.push(json!({"date": probe.to_string(), "weekday": probe.format("%A").to_string(), "first_slot": local_hm(tz, *first)}));
        }
        probe += Duration::days(1);
    }
    Ok(
        json!({"ok": true, "date": day.to_string(), "weekday": weekday, "slots": [], "message": "No free times that day.", "next_available_dates": upcoming}),
    )
}

/// `datetime.fromisoformat(value.strip().replace(" ", "T"))`: `Ok(None)` is ValueError; `Some((naive, has_offset))`.
fn parse_local(text: &str) -> Result<Option<(NaiveDateTime, bool)>, Unsupported> {
    static MAIN: OnceLock<Regex> = OnceLock::new();
    static LOOSE: OnceLock<Regex> = OnceLock::new();
    let main = MAIN.get_or_init(|| Regex::new(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:T([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{1,6}))?)?)?(Z|[+-][0-9]{2}:[0-9]{2})?$").unwrap());
    let loose = LOOSE.get_or_init(|| Regex::new(r"^[0-9]{4}[-[0-9]WT:.,+Z]*$").unwrap());
    let t = py_strip(text).replace(' ', "T");
    if let Some(c) = main.captures(&t) {
        let n = |i: usize| c.get(i).map_or(0u32, |m| m.as_str().parse().unwrap());
        let date = NaiveDate::from_ymd_opt(n(1) as i32, n(2), n(3));
        let time = NaiveTime::from_hms_micro_opt(
            n(4),
            n(5),
            n(6),
            c.get(7)
                .map_or(0, |m| format!("{:0<6}", m.as_str()).parse().unwrap()),
        );
        return Ok(match (date, time) {
            (Some(d), Some(tm)) => Some((d.and_time(tm), c.get(8).is_some())),
            _ => None,
        });
    }
    if loose.is_match(&t) && t.chars().count() >= 8 {
        return Err(Unsupported("alternative ISO datetime form"));
    }
    Ok(None)
}

fn s_of(v: Option<&Value>) -> Result<String, Unsupported> {
    str_or_empty(v).ok_or(Unsupported("argument needs a Python repr"))
}

fn take(s: &str, n: usize) -> String {
    py_strip(s).chars().take(n).collect()
}

fn err(msg: &str) -> Result<Value, Unsupported> {
    Ok(json!({"ok": false, "error": msg}))
}

/// `book(tenant, args, ctx)`. `ctx` is updated exactly as Python's is.
pub fn book(
    env: &mut dyn Env,
    tenant: &Value,
    args: &Value,
    ctx: &mut Map<String, Value>,
    default_cc: &str,
) -> Result<Value, Unsupported> {
    let tz = tenant_tz(tenant);
    let start_text = s_of(args.get("start"))?;
    let Some((start_local, has_offset)) = parse_local(&start_text)? else {
        return err("start must look like 2026-11-05 14:30 (business local time)");
    };
    let name = take(&s_of(args.get("name"))?, 120);
    let phone_value = if truthy(args.get("phone")) {
        args.get("phone")
    } else {
        ctx.get("sender_phone")
    };
    let phone_raw = take(&s_of(phone_value)?, 40);
    let email = take(&s_of(args.get("email"))?, 200);
    let notes = take(&s_of(args.get("notes"))?, 500);
    let consent = truthy(args.get("consent_to_contact")) || truthy(ctx.get("sms_inbound"));
    let phone = normalize_phone(&phone_raw, default_cc).unwrap_or_default();
    if name.is_empty() {
        return err("Need the visitor's name.");
    }
    if phone.is_empty() && !is_email(&email) {
        return err("Need a valid phone number or email so we can confirm.");
    }
    if has_offset {
        return err("Use business local time without a UTC offset");
    }
    let Some(start_utc) = local_to_utc(tz, start_local) else {
        return err("That local time does not exist because of daylight saving");
    };
    // a fall-back overlap resolves to its first occurrence, which round-trips; a spring-forward gap does not exist
    let tid = tenant["id"].as_str().unwrap_or("").to_string();
    let conversation_id: Option<String> = match ctx.get("conversation_id") {
        Some(Value::String(c)) if !c.is_empty() => Some(c.clone()),
        _ => None,
    };
    let email_clean = if is_email(&email) {
        email.clone()
    } else {
        String::new()
    };
    if let Some(cid) = &conversation_id {
        if args.get("confirmed") == Some(&Value::Bool(true)) {
            if let Some(prev) = env.previous_booking(&tid, cid, start_utc) {
                if prev["status"] != "booked" {
                    return err("That earlier booking is no longer active. Ask the team to reschedule or choose a new time.");
                }
                if prev["name"] != json!(name)
                    || prev["email"] != json!(email_clean)
                    || prev["phone"] != json!(phone)
                {
                    return err(
                        "A different booking already exists for this conversation and time",
                    );
                }
                return Ok(appointment_result(tz, &prev, true));
            }
        }
    }
    let free = slots_on(env, tenant, start_local.date(), false)?;
    if !free.contains(&start_utc) {
        return err("That time is not available. Call check_availability and offer a listed slot.");
    }
    let key = json!({"start": iso(start_utc), "name": name.to_lowercase(), "email": email.to_lowercase(), "phone": phone, "consent": consent});
    let pending = conversation_id.as_ref().map(|c| env.pending(c));
    if !(args.get("confirmed") == Some(&Value::Bool(true)) && pending.as_ref() == Some(&key)) {
        if let Some(cid) = &conversation_id {
            env.set_pending(cid, key);
        }
        let wher = if phone.is_empty() { &email } else { &phone };
        return Ok(json!({
            "ok": false, "needs_confirmation": true,
            "read_back": format!("{name}, {}. We'll confirm with you at {wher}.", fmt_local(tz, start_utc)),
            "instruction": "Read this back to the visitor and ask them to confirm. Only after they clearly say yes, call book_appointment again with exactly the same start and name and confirmed=true.",
        }));
    }
    if truthy(ctx.get("dry_run")) {
        return Ok(json!({"ok": true, "confirmation": "(dry run) booking would be created"}));
    }
    let end_utc = start_utc + Duration::minutes(tenant["slot_minutes"].as_i64().unwrap_or(30));
    env.lock_tenant(&tid);
    if !slots_on(env, tenant, start_local.date(), true)?.contains(&start_utc) {
        return err("Sorry, that time was just taken. Call check_availability for other times.");
    }
    let existing = conversation_id
        .as_ref()
        .and_then(|c| env.existing_lead(&tid, c));
    let lead = match existing {
        Some(l) => l,
        None => {
            let message = py_strip(&format!(
                "Booked appointment for {}. {notes}",
                fmt_local(tz, start_utc)
            ))
            .to_string();
            let utm = ctx
                .get("utm")
                .filter(|u| truthy(Some(u)))
                .cloned()
                .unwrap_or_else(|| json!({}));
            let utm_json = crate::pyjson::dumps(&utm).ok_or(Unsupported("float in utm"))?;
            let channel = ctx
                .get("channel")
                .and_then(Value::as_str)
                .unwrap_or("chat")
                .to_string();
            let page_url = ctx.get("page_url").cloned().unwrap_or(Value::Null);
            let hook = if truthy(tenant.get("lead_webhook_url")) {
                "pending"
            } else {
                "none"
            };
            env.insert_lead(
                &tid,
                conversation_id.as_deref(),
                &name,
                &email_clean,
                &phone,
                &message,
                &channel,
                &page_url,
                &utm_json,
                hook,
                consent,
            )
        }
    };
    let appt = env.insert_appointment(
        &tid,
        &lead["id"],
        conversation_id.as_deref(),
        start_utc,
        end_utc,
        &name,
        &phone,
        &email_clean,
        &notes,
        consent,
    );
    if let Some(cid) = &conversation_id {
        env.set_pending(cid, Value::Null);
    }
    env.sync_one(&appt["id"]);
    let appt = env.refetch(&tid, &appt["id"]);
    env.notify_synced(&appt["id"]);
    let result = appointment_result(tz, &appt, false);
    ctx.insert("appointment_text".into(), result["confirmation"].clone());
    ctx.insert("lead_captured".into(), json!(true));
    Ok(result)
}

fn appointment_result(tz: Tz, appt: &Value, duplicate: bool) -> Value {
    let starts = appt["starts_at"]
        .as_str()
        .and_then(|s| DateTime::parse_from_rfc3339(s).ok())
        .map(|d| d.with_timezone(&Utc))
        .unwrap_or_default();
    let id = match &appt["id"] {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    };
    booking_result(
        tz,
        &Appointment {
            id: &id,
            starts_at: starts,
            calendar_state: appt["calendar_state"].as_str(),
            invitation_state: appt["invitation_state"].as_str(),
        },
        duplicate,
    )
}
