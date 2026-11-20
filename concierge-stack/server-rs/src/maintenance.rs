//! Provider-free maintenance with explicit bounded owner-auth cleanup.
use crate::State;
use concierge_core::maintenance;
use serde_json::{json, Map, Value};
use std::time::Duration;
use tokio::sync::watch;

pub async fn prune_auth(state: &State, batch_size: i64, dry_run: bool) -> Result<Value, String> {
    maintenance::check_batch_size(batch_size).map_err(str::to_owned)?;
    let pool = state.0.pool.as_ref().ok_or("database unavailable")?;
    let mut c = pool.get().await.map_err(|e| e.to_string())?;
    let tx = c.transaction().await.map_err(|e| e.to_string())?;
    let mut counts = Map::new();
    for (table, predicate) in maintenance::TABLES {
        let count = if dry_run {
            tx.query_one(&format!("SELECT count(*) FROM (SELECT 1 FROM {table} WHERE {predicate} LIMIT $1) AS candidates"),&[&batch_size]).await.map_err(|e|e.to_string())?.get::<_,i64>(0)
        } else {
            tx.query(&format!("DELETE FROM {table} WHERE ctid IN (SELECT ctid FROM {table} WHERE {predicate} LIMIT $1 FOR UPDATE SKIP LOCKED) RETURNING 1"),&[&batch_size]).await.map_err(|e|e.to_string())?.len() as i64
        };
        counts.insert(table.to_owned(), json!(count));
    }
    tx.commit().await.map_err(|e| e.to_string())?;
    Ok(json!({"mode":if dry_run{"dry_run"}else{"apply"},"eligible":counts}))
}

pub async fn purge_voice(state: &State) -> Result<(), String> {
    let pool = state.0.pool.as_ref().ok_or("database unavailable")?;
    let c = pool.get().await.map_err(|e| e.to_string())?;
    for sql in [
        "DELETE FROM voice_recordings WHERE created_at<now()-interval '30 days'",
        "DELETE FROM voice_recording_shares WHERE expires_at<now()",
        "DELETE FROM voice_sessions WHERE created_at<now()-interval '30 days'",
    ] {
        c.execute(sql, &[]).await.map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Stop is observed both before a sweep and while sleeping. Failed sweeps retry at the normal cadence.
pub async fn voice_worker(state: State, mut stop: watch::Receiver<bool>, interval: Duration) {
    loop {
        if *stop.borrow() {
            return;
        }
        if let Err(e) = purge_voice(&state).await {
            eprintln!("Voice recording retention cleanup will retry: {e}");
        }
        tokio::select! {_ =tokio::time::sleep(interval)=>{},changed=stop.changed()=>{if changed.is_err()||*stop.borrow(){return;}}}
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn pre_stopped_worker_never_touches_unavailable_database() {
        let (tx, rx) = watch::channel(true);
        let state = State::without_database(crate::Config::from_env());
        tokio::time::timeout(
            Duration::from_millis(100),
            voice_worker(state, rx, Duration::from_secs(3600)),
        )
        .await
        .unwrap();
        drop(tx);
    }
    #[tokio::test]
    async fn failed_sweep_still_stops_promptly() {
        let (tx, rx) = watch::channel(false);
        let state = State::without_database(crate::Config::from_env());
        let worker = tokio::spawn(voice_worker(state, rx, Duration::from_secs(3600)));
        tokio::task::yield_now().await;
        tx.send(true).unwrap();
        tokio::time::timeout(Duration::from_millis(100), worker)
            .await
            .unwrap()
            .unwrap();
    }
}
