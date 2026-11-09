//! To-do rules (port of the pure parts of `tasks.py`).
use crate::py_strip;
use crate::schedule::local_to_utc;
use chrono::{DateTime, Duration, NaiveTime, TimeZone, Utc};
use chrono_tz::Tz;

/// When a new lead's follow-up should happen: an hour (or the SLA) for a hot lead, otherwise 9am next morning.
pub fn default_follow_up_due(
    tz: Tz,
    sla_minutes: Option<i64>,
    hot: bool,
    now: DateTime<Utc>,
) -> DateTime<Utc> {
    if hot {
        let minutes = sla_minutes.filter(|m| *m != 0).unwrap_or(60);
        return now + Duration::minutes(minutes);
    }
    let local = now.with_timezone(&tz).naive_local();
    let nine = local
        .date()
        .and_time(NaiveTime::from_hms_opt(9, 0, 0).unwrap());
    // Python compares wall-clock fields (same tzinfo) and adds days to the wall clock, not 24 absolute hours.
    let target = if local >= nine {
        nine + Duration::days(1)
    } else {
        nine
    };
    local_to_utc(tz, target).unwrap_or_else(|| tz.from_utc_datetime(&target).with_timezone(&Utc))
}

pub fn clean_title(title: &str) -> Result<String, &'static str> {
    let t = py_strip(title);
    if t.is_empty() {
        return Err("A to-do needs a title");
    }
    if t.chars().count() > 200 {
        return Err("Title is too long (200 characters max)");
    }
    Ok(t.to_string())
}
