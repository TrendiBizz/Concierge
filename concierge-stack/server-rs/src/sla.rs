//! Response-time alerts: same tenant predicates, exclusions and durable queue as Python.
use crate::State;
use chrono::{DateTime, Utc};
use concierge_core::{contact, schedule, sla};
use std::time::Duration;
use tokio::sync::watch;

pub async fn check_once(state: &State) -> Result<u64, String> {
    let pool = state.0.pool.as_ref().ok_or("database unavailable")?;
    let c = pool.get().await.map_err(|e| e.to_string())?;
    let tenants = c.query("SELECT id,name,notify_email,timezone,sla_minutes,sla_min_score FROM tenants WHERE sla_minutes>0 AND notify_email IS NOT NULL AND notify_email<>''", &[]).await.map_err(|e|e.to_string())?;
    let mut queued = 0;
    for tenant in tenants {
        let to: String = tenant.get("notify_email");
        if !contact::is_email(&to) {
            continue;
        }
        let tz: chrono_tz::Tz = tenant
            .get::<_, String>("timezone")
            .parse()
            .map_err(|e| format!("invalid timezone: {e}"))?;
        let now = c
            .query_one("SELECT clock_timestamp()", &[])
            .await
            .map_err(|e| e.to_string())?
            .get::<_, DateTime<Utc>>(0);
        let send_at = schedule::next_allowed_send(tz, now, 8, 21);
        let tid: uuid::Uuid = tenant.get("id");
        let minutes: i32 = tenant.get("sla_minutes");
        let min_score: i32 = tenant.get::<_, Option<i32>>("sla_min_score").unwrap_or(70);
        let leads=c.query("SELECT id,name,phone,email,message,channel,score,score_label,floor(EXTRACT(EPOCH FROM (now()-created_at))/60)::int AS minutes_waiting FROM leads WHERE tenant_id=$1 AND status='new' AND ($3<=0 OR score>=$3) AND created_at<now()-make_interval(mins=>$2) AND created_at>now()-interval '2 days' AND NOT EXISTS(SELECT 1 FROM appointments a WHERE a.lead_id=leads.id AND a.status IN ('booked','completed')) AND NOT EXISTS(SELECT 1 FROM customer_cases c WHERE c.id=leads.case_id AND c.automation_paused) AND NOT EXISTS(SELECT 1 FROM opt_outs o WHERE o.tenant_id=leads.tenant_id AND o.contact=ANY(ARRAY[CASE WHEN leads.email<>'' THEN lower(leads.email) END,CASE WHEN leads.phone<>'' THEN leads.phone END])) AND sla_alerted_at IS NULL ORDER BY score DESC,created_at LIMIT 100",&[&tid,&minutes,&min_score]).await.map_err(|e|e.to_string())?;
        let name: String = tenant.get("name");
        for lead in leads {
            let id: uuid::Uuid = lead.get("id");
            let lead_name: Option<String> = lead.get("name");
            let phone: Option<String> = lead.get("phone");
            let email: Option<String> = lead.get("email");
            let message: Option<String> = lead.get("message");
            let channel: Option<String> = lead.get("channel");
            let label: String = lead.get("score_label");
            let (subject, body) = sla::alert_text(
                &sla::Tenant {
                    name: &name,
                    sla_minutes: minutes.into(),
                },
                &sla::Lead {
                    name: lead_name.as_deref(),
                    phone: phone.as_deref(),
                    email: email.as_deref(),
                    message: message.as_deref(),
                    channel: channel.as_deref(),
                    score_label: &label,
                    score: i64::from(lead.get::<_, i32>("score")),
                    minutes_waiting: i64::from(lead.get::<_, i32>("minutes_waiting")),
                },
            );
            let dedupe = format!("lead:{id}:sla");
            c.execute("INSERT INTO outbox(tenant_id,kind,channel,to_addr,subject,body,send_at,dedupe_key,lead_id) VALUES($1,'owner_alert','email',$2,$3,$4,$5,$6,$7) ON CONFLICT(dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING",&[&tid,&to,&subject,&body,&send_at,&dedupe,&id]).await.map_err(|e|e.to_string())?;
            c.execute(
                "UPDATE leads SET sla_alerted_at=now() WHERE id=$1 AND tenant_id=$2",
                &[&id, &tid],
            )
            .await
            .map_err(|e| e.to_string())?;
            queued += 1;
        }
    }
    Ok(queued)
}
pub async fn worker(state: State, mut stop: watch::Receiver<bool>, interval: Duration) {
    let interval = interval.max(Duration::from_secs(10));
    loop {
        if *stop.borrow() {
            return;
        }
        if let Err(e) = check_once(&state).await {
            eprintln!("SLA loop will retry: {e}");
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
