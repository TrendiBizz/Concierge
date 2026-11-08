//! Concierge Social: independent Rust HTTP service for guarded social posting.
//! Built from official platform API specifications, not Postiz implementation.
//! Live publishing is disabled by default.

pub mod adaptation;
pub mod api;
pub mod bluesky;
pub mod composer;
pub mod connector;
pub mod google_business;
pub mod google_business_publish;
pub mod guardrails;
pub mod linkedin;
pub mod linkedin_media;
pub mod linkedin_pages;
pub mod media;
pub mod meta;
pub mod meta_publish;
pub mod model;
pub mod oauth;
pub mod scheduler;
pub mod social_publish;
pub mod store;
pub mod tiktok;
pub mod tiktok_publish;
pub mod token_refresh;
pub mod vault;

pub fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}
