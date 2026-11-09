//! SMS shortening for owner notices (port of `owner_notifications.sms_body`).
use crate::pyval::truncate_chars;
use regex::Regex;
use std::sync::OnceLock;

fn link_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"https?://[^\s]+/recordings/shared/[^\s]+").unwrap())
}

pub fn sms_body(subject: &str, body: &str, public_base_url: &str) -> String {
    if body.chars().count() <= 1400 {
        return body.to_string();
    }
    let mut suffix = format!(
        "\nFull original conversation in your private portal: {}/owner-ui",
        public_base_url.trim_end_matches('/')
    );
    if let Some(last) = link_re().find_iter(body).last() {
        suffix.push_str(&format!("\nRecording: {}", last.as_str()));
    }
    let keep = 1400_i64 - suffix.chars().count() as i64 - 162;
    format!(
        "{}\n{}{suffix}",
        truncate_chars(subject, 160),
        truncate_chars(body, keep.max(0) as usize)
    )
}
