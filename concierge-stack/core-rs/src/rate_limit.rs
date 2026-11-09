use std::collections::{HashMap, VecDeque};
use std::time::{Duration, Instant};

/// Sliding-window limiter held in process memory. Wrap in a `Mutex` to share between tasks.
pub struct RateLimiter {
    limit: usize,
    window: Duration,
    hits: HashMap<String, VecDeque<Instant>>,
}

impl RateLimiter {
    pub fn new(limit: usize, window: Duration) -> Self {
        Self { limit, window, hits: HashMap::new() }
    }

    pub fn check(&mut self, key: &str, now: Instant) -> bool {
        let window = self.window;
        let q = self.hits.entry(key.to_string()).or_default();
        while q.front().is_some_and(|t| now.duration_since(*t) >= window) {
            q.pop_front();
        }
        if q.len() >= self.limit {
            return false;
        }
        q.push_back(now);
        if self.hits.len() > 20_000 {
            self.prune(now);
        }
        true
    }

    fn prune(&mut self, now: Instant) {
        let window = self.window;
        self.hits.retain(|_, q| q.back().is_some_and(|t| now.duration_since(*t) < window));
    }
}
