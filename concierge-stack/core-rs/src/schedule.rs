//! Time-zone aware scheduling: the allowed sending window (`outbox.next_allowed_send`) and free
//! booking slots (`booking.day_slots`). DST gaps drop the slot; ambiguous times use the first occurrence,
//! exactly as Python's `zoneinfo` does with `fold=0`.
use chrono::{
    DateTime, Datelike, Duration, LocalResult, NaiveDate, NaiveDateTime, NaiveTime, TimeZone,
    Timelike, Utc,
};
use chrono_tz::Tz;
use std::collections::BTreeMap;

fn local_to_utc(tz: Tz, naive: NaiveDateTime) -> Option<DateTime<Utc>> {
    match tz.from_local_datetime(&naive) {
        LocalResult::Single(d) => Some(d.with_timezone(&Utc)),
        LocalResult::Ambiguous(first, _) => Some(first.with_timezone(&Utc)),
        LocalResult::None => None,
    }
}

/// Move `when` to the next moment inside the allowed window (local time).
pub fn next_allowed_send(
    tz: Tz,
    when: DateTime<Utc>,
    start_hour: u32,
    end_hour: u32,
) -> DateTime<Utc> {
    let local = when.with_timezone(&tz);
    if (start_hour..end_hour).contains(&local.hour()) {
        return when;
    }
    let date = local.date_naive();
    let day = if local.hour() < start_hour {
        date
    } else {
        date + Duration::days(1)
    };
    let naive = day.and_time(NaiveTime::from_hms_opt(start_hour, 0, 0).expect("valid hour"));
    local_to_utc(tz, naive).unwrap_or_else(|| {
        // The wall time does not exist (DST gap): Python applies the offset in force before the gap.
        let before = tz
            .offset_from_local_datetime(&(naive - Duration::days(1)))
            .earliest()
            .expect("offset");
        let off = chrono::offset::Offset::fix(&before);
        (naive - Duration::seconds(off.local_minus_utc() as i64)).and_utc()
    })
}

pub struct BookingTenant {
    pub timezone: Tz,
    pub slot_minutes: i64,
    pub min_notice_hours: i64,
    /// "mon".."sun" -> [(open "HH:MM", close "HH:MM")]
    pub business_hours: BTreeMap<String, Vec<(String, String)>>,
}

const DAYS: [&str; 7] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

fn hm(value: &str) -> Result<NaiveTime, String> {
    let (h, m) = value
        .split_once(':')
        .ok_or_else(|| format!("bad time '{value}'"))?;
    if m.contains(':') {
        return Err(format!("bad time '{value}'"));
    }
    let parse = |s: &str| {
        s.trim()
            .parse::<u32>()
            .map_err(|_| format!("bad time '{value}'"))
    };
    NaiveTime::from_hms_opt(parse(h)?, parse(m)?, 0).ok_or_else(|| format!("bad time '{value}'"))
}

/// Free slot start times (UTC) for one local calendar day.
pub fn day_slots(
    tenant: &BookingTenant,
    day: NaiveDate,
    now_utc: DateTime<Utc>,
    booked: &[(DateTime<Utc>, DateTime<Utc>)],
) -> Result<Vec<DateTime<Utc>>, String> {
    if tenant.slot_minutes <= 0 {
        return Err("slot_minutes must be positive".into());
    }
    let step = Duration::minutes(tenant.slot_minutes);
    let earliest = now_utc + Duration::hours(tenant.min_notice_hours);
    let mut slots = Vec::new();
    let windows = tenant
        .business_hours
        .get(DAYS[day.weekday().num_days_from_monday() as usize]);
    for (opens, closes) in windows.into_iter().flatten() {
        let mut cursor = day.and_time(hm(opens)?);
        let end = day.and_time(hm(closes)?);
        while cursor + step <= end {
            if let Some(start_utc) = local_to_utc(tenant.timezone, cursor) {
                let end_utc = start_utc + step;
                let clash = booked
                    .iter()
                    .any(|(bs, be)| *bs < end_utc && *be > start_utc);
                if start_utc >= earliest && !clash {
                    slots.push(start_utc);
                }
            }
            cursor += step;
        }
    }
    Ok(slots)
}
