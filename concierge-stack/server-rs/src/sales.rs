//! Pipeline and scheduled owner summaries. Notifications are durable outbox entries.
use crate::{owner, row_json, server_error, State};
use axum::{
    extract::State as AxState,
    http::HeaderMap,
    response::{IntoResponse, Response},
    Json,
};
use chrono::{DateTime, Datelike, Timelike, Utc};
use concierge_core::{contact, sales};
use serde_json::Value;
use std::time::Duration;
use tokio::sync::watch;
use tokio_postgres::Client;

async fn board(
    c: &Client,
    tid: &uuid::Uuid,
    average: i64,
    per_stage: usize,
) -> Result<Value, String> {
    let rows=c.query("SELECT id,name,phone,email,message,channel,status,score,score_label,value_cents,next_action_at,lost_reason,won_at,lost_at,created_at FROM leads WHERE tenant_id=$1 AND (status NOT IN ('won','lost') OR updated_at>now()-interval '30 days') ORDER BY score DESC,created_at DESC LIMIT 1000",&[tid]).await.map_err(|e|e.to_string())?;
    let mut result = sales::forecast(
        &rows.iter().map(row_json).collect::<Vec<_>>(),
        Some(average),
        per_stage,
    );
    result["average_lead_value_cents"] = serde_json::json!(average);
    Ok(result)
}
pub(crate) async fn pipeline(AxState(state): AxState<State>, headers: HeaderMap) -> Response {
    let u = match owner::current_user(&state, &headers).await {
        Ok(u) => u,
        Err(e) => return e.response(),
    };
    let Some(pool) = &state.0.pool else {
        return server_error();
    };
    let Ok(c) = pool.get().await else {
        return server_error();
    };
    let average = match c
        .query_one(
            "SELECT lead_value_cents FROM tenants WHERE id=$1",
            &[&u.tenant_id],
        )
        .await
    {
        Ok(r) => r.get::<_, Option<i64>>(0).unwrap_or(0),
        Err(_) => return server_error(),
    };
    match board(&c, &u.tenant_id, average, 50).await {
        Ok(v) => Json(v).into_response(),
        Err(_) => server_error(),
    }
}
async fn summary(
    c: &Client,
    tid: &uuid::Uuid,
    average: i64,
    minutes: i32,
    min_score: i32,
    days: i32,
) -> Result<sales::Summary, String> {
    let new_leads=c.query_one("SELECT count(*) FROM leads WHERE tenant_id=$1 AND created_at>now()-make_interval(days=>$2)",&[tid,&days]).await.map_err(|e|e.to_string())?.get(0);
    let moved=c.query("SELECT to_status,count(*) AS n FROM lead_events WHERE tenant_id=$1 AND created_at>now()-make_interval(days=>$2) GROUP BY to_status",&[tid,&days]).await.map_err(|e|e.to_string())?;
    let count = |stage: &str| {
        moved
            .iter()
            .find(|r| r.get::<_, String>("to_status") == stage)
            .map_or(0, |r| r.get::<_, i64>("n"))
    };
    let won_rows=c.query("SELECT value_cents FROM leads WHERE tenant_id=$1 AND status='won' AND won_at>now()-make_interval(days=>$2)",&[tid,&days]).await.map_err(|e|e.to_string())?;
    let won_value_cents = won_rows
        .iter()
        .map(|r| {
            i128::from(
                r.get::<_, Option<i64>>(0)
                    .filter(|n| *n != 0)
                    .unwrap_or(average),
            )
        })
        .sum();
    let board = board(c, tid, average, 0).await?;
    let open_value_cents = board["open_value_cents"]
        .to_string()
        .parse()
        .map_err(|_| "invalid pipeline total")?;
    let weighted_value_cents = board["weighted_value_cents"]
        .to_string()
        .parse()
        .map_err(|_| "invalid weighted total")?;
    let overdue_todos = c
        .query_one(
            "SELECT count(*) FROM tasks WHERE tenant_id=$1 AND status='open' AND due_at<now()",
            &[tid],
        )
        .await
        .map_err(|e| e.to_string())?
        .get(0);
    let leads_waiting = if minutes != 0 {
        Some(
            crate::sla::overdue(c, tid, minutes, min_score, 7, false)
                .await?
                .len() as i64,
        )
    } else {
        None
    };
    Ok(sales::Summary {
        days: days.into(),
        new_leads,
        contacted: count("contacted"),
        booked: count("booked"),
        won: won_rows.len() as i64,
        lost: count("lost"),
        won_value_cents,
        open_value_cents,
        weighted_value_cents,
        overdue_todos,
        leads_waiting,
    })
}
/// Optional clock makes local-day/week boundaries verifiable without sleeping or changing the host clock.
pub async fn check_summaries(state: &State, now: Option<DateTime<Utc>>) -> Result<u64, String> {
    let pool = state.0.pool.as_ref().ok_or("database unavailable")?;
    let c = pool.get().await.map_err(|e| e.to_string())?;
    let now = match now {
        Some(n) => n,
        None => c
            .query_one("SELECT clock_timestamp()", &[])
            .await
            .map_err(|e| e.to_string())?
            .get(0),
    };
    let mut queued = 0;
    // Python checks weekly summaries before daily summaries, including failure ordering.
    for daily in [false, true] {
        let rows=c.query("SELECT id,name,notify_email,timezone,lead_value_cents,sla_minutes,sla_min_score FROM tenants WHERE (CASE WHEN $1 THEN daily_summary ELSE weekly_digest END)=true AND notify_email IS NOT NULL AND notify_email<>''",&[&daily]).await.map_err(|e|e.to_string())?;
        for t in rows {
            let to: String = t.get("notify_email");
            if !contact::is_email(&to) {
                continue;
            }
            let tz: chrono_tz::Tz = t
                .get::<_, String>("timezone")
                .parse()
                .map_err(|e| format!("invalid timezone: {e}"))?;
            let local = now.with_timezone(&tz);
            if if daily {
                !sales::daily_is_due(local.hour())
            } else {
                !sales::digest_is_due(local.weekday().num_days_from_monday(), local.hour())
            } {
                continue;
            }
            let tid: uuid::Uuid = t.get("id");
            let week = local.iso_week();
            let key = if daily {
                format!("daily:{tid}:{}", local.date_naive())
            } else {
                format!("digest:{tid}:{}-W{:02}", week.year(), week.week())
            };
            if c.query_opt("SELECT 1 FROM outbox WHERE dedupe_key=$1", &[&key])
                .await
                .map_err(|e| e.to_string())?
                .is_some()
            {
                continue;
            }
            let s = summary(
                &c,
                &tid,
                t.get::<_, Option<i64>>("lead_value_cents").unwrap_or(0),
                t.get::<_, Option<i32>>("sla_minutes").unwrap_or(0),
                t.get::<_, Option<i32>>("sla_min_score").unwrap_or(70),
                if daily { 1 } else { 7 },
            )
            .await?;
            let name: String = t.get("name");
            let note = if daily {
                sales::daily_text(&name, &s)
            } else {
                Some(sales::digest_text(&name, &s))
            };
            if let Some((subject, body)) = note {
                queued+=c.execute("INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,send_at,dedupe_key) VALUES($1,'owner_alert','email',$2,$3,$4,now(),$5) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",&[&tid,&to,&subject,&body,&key]).await.map_err(|e|e.to_string())?;
            }
        }
    }
    Ok(queued)
}
pub async fn worker(state: State, mut stop: watch::Receiver<bool>, interval: Duration) {
    let interval = interval.max(Duration::from_secs(30));
    loop {
        if *stop.borrow() {
            return;
        }
        if let Err(e) = check_summaries(&state, None).await {
            eprintln!("Digest loop will retry: {e}");
        }
        tokio::select! {_=tokio::time::sleep(interval)=>{},changed=stop.changed()=>{if changed.is_err()||*stop.borrow(){return;}}}
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn stopped_and_failing_worker_shutdown() {
        for stopped in [true, false] {
            let (tx, rx) = watch::channel(stopped);
            let state = State::without_database(crate::Config::from_env());
            let handle = tokio::spawn(worker(state, rx, Duration::from_secs(3600)));
            if !stopped {
                tokio::task::yield_now().await;
                tx.send(true).unwrap();
            }
            tokio::time::timeout(Duration::from_millis(100), handle)
                .await
                .unwrap()
                .unwrap();
        }
    }
}
