//! One brief, tenant-scoped destination previews. No publishing or approval here.
//! Adaptations are explicit and editable; shortening and omitted assets are disclosed.
use crate::{
    guardrails::{check_post, PostInput, Rules},
    model::Account,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

pub const NETWORKS: &[&str] = &[
    "facebook",
    "instagram",
    "linkedin",
    "linkedin_organization",
    "tiktok",
    "google_business",
];
#[derive(Clone, Debug, Deserialize)]
pub struct Brief {
    pub content: String,
    pub account_ids: Vec<String>,
    #[serde(default)]
    pub link: String,
    #[serde(default)]
    pub hashtags: String,
    #[serde(default)]
    pub media: Vec<String>,
    #[serde(default)]
    pub video: Option<String>,
}
#[derive(Debug, Serialize)]
pub struct Variant {
    pub account_id: String,
    pub account_name: String,
    pub network: String,
    pub content: String,
    pub link: String,
    pub hashtags: String,
    pub media: Vec<String>,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
    pub length: usize,
    pub limit: usize,
    pub tiktok_creator: Option<crate::tiktok_publish::Creator>,
}
fn shorten(text: &str, limit: usize) -> (String, bool) {
    if text.encode_utf16().count() <= limit {
        return (text.to_string(), false);
    }
    let mut result = String::new();
    for word in text.split_whitespace() {
        let candidate = if result.is_empty() {
            word.into()
        } else {
            format!("{result} {word}")
        };
        if candidate.encode_utf16().count() + 1 > limit {
            break;
        }
        result = candidate;
    }
    if result.is_empty() {
        for ch in text.chars() {
            if result.encode_utf16().count() + ch.len_utf16() + 1 > limit {
                break;
            }
            result.push(ch);
        }
    }
    result.push('…');
    (result, true)
}
pub fn compose(brief: &Brief, accounts: &[Account], rules: &Rules) -> Result<Vec<Variant>, String> {
    if brief.content.trim().is_empty()
        || brief.content.len() > 40000
        || brief.content.chars().count() > 10000
        || brief.account_ids.is_empty()
        || brief.account_ids.len() > 10
        || brief.media.len() > 10
    {
        return Err("Enter a post and select between one and ten accounts".into());
    }
    for url in brief
        .media
        .iter()
        .chain(brief.video.iter())
        .chain(std::iter::once(&brief.link))
        .filter(|u| !u.is_empty())
    {
        if url.starts_with("upload:")
            && url[7..].len() >= 20
            && url[7..].len() <= 128
            && url[7..]
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        {
            continue;
        }
        let parsed =
            reqwest::Url::parse(url).map_err(|_| "Use valid HTTPS links and media URLs")?;
        if parsed.scheme() != "https"
            || parsed.host_str().is_none()
            || !parsed.username().is_empty()
            || parsed.password().is_some()
            || url.len() > 2048
        {
            return Err("Use valid HTTPS links and media URLs".into());
        }
    }
    let unique: BTreeSet<_> = brief.account_ids.iter().collect();
    if unique.len() != brief.account_ids.len() {
        return Err("An account was selected more than once".into());
    }
    let mut result = Vec::new();
    for id in &brief.account_ids {
        let account = accounts
            .iter()
            .find(|a| &a.id == id)
            .ok_or("Selected account is not available for this business")?;
        if !NETWORKS.contains(&account.network.as_str()) {
            return Err("This platform is not offered in Concierge".into());
        }
        let network = account.network.as_str();
        let limit = match network {
            "facebook" => 63206,
            "google_business" => 1500,
            "linkedin" | "linkedin_organization" => 3000,
            _ => 2200,
        };
        let mut warnings = Vec::new();
        let mut errors = Vec::new();
        if account.needs_reauth {
            errors.push("Reconnect this account before scheduling".into());
        }
        let mut link = brief.link.trim().to_string();
        let max_tags = match network {
            "google_business" => 0,
            "linkedin" | "linkedin_organization" => 3,
            _ => 5,
        };
        let mut seen = BTreeSet::new();
        let tags: Vec<_> = brief
            .hashtags
            .split_whitespace()
            .filter(|tag| tag.starts_with('#') && seen.insert(tag.to_lowercase()))
            .collect();
        if tags.len() > max_tags {
            warnings.push(format!(
                "Hashtags reduced to {max_tags} for this destination; review before approval"
            ));
        }
        let hashtags = tags
            .into_iter()
            .take(max_tags)
            .collect::<Vec<_>>()
            .join(" ");
        if network == "instagram" && !link.is_empty() {
            warnings.push("Instagram caption links are not clickable; add the destination to your profile if needed".into());
        }
        let media = match network {
            "tiktok" => {
                if let Some(video) = &brief.video {
                    if !video.starts_with("upload:") {
                        errors.push(
                            "Upload the TikTok video for server duration verification".into(),
                        );
                    }
                    vec![video.clone()]
                } else {
                    errors.push("Add a video for TikTok".into());
                    vec![]
                }
            }
            "google_business" => {
                if brief.media.is_empty() && brief.video.is_some() {
                    warnings.push("Google Business uses a still image from your video; review it before approval".into());
                }
                brief.media.iter().take(1).cloned().collect()
            }
            _ => {
                if brief.media.len() > 1 {
                    warnings.push("The first image is selected for this destination".into());
                }
                let chosen = brief
                    .media
                    .first()
                    .or(brief.video.as_ref())
                    .cloned()
                    .into_iter()
                    .collect::<Vec<_>>();
                if network == "instagram" && chosen.is_empty() {
                    errors.push("Add an image or video for Instagram".into());
                }
                chosen
            }
        };
        if network == "google_business" && !link.is_empty() {
            warnings.push(
                "The link is retained in the Google Business update; review the complete preview"
                    .into(),
            );
        }
        let reserved = link.encode_utf16().count()
            + hashtags.encode_utf16().count()
            + usize::from(!link.is_empty())
            + usize::from(!hashtags.is_empty());
        if reserved + 8 >= limit {
            return Err("Link and hashtags leave no room for the post".into());
        }
        let (content, shortened) = shorten(brief.content.trim(), limit - reserved);
        if shortened {
            warnings.push(
                "This version was shortened to fit. Review that no important detail was removed"
                    .into(),
            );
        }
        let rules_network = if network == "linkedin_organization" {
            "linkedin"
        } else {
            network
        };
        let check = check_post(
            &PostInput {
                content: content.clone(),
                link: link.clone(),
                hashtags: hashtags.clone(),
                networks: vec![rules_network.into()],
                media_count: media.len(),
            },
            rules,
        );
        errors.extend(check.errors.into_iter().map(|e| e.message));
        warnings.extend(check.warnings.into_iter().map(|e| e.message));
        let length = content.encode_utf16().count() + reserved;
        result.push(Variant {
            account_id: id.clone(),
            account_name: account.display_name.clone(),
            network: network.into(),
            content,
            link: std::mem::take(&mut link),
            hashtags,
            media,
            warnings,
            errors,
            length,
            limit,
            tiktok_creator: None,
        });
    }
    Ok(result)
}
#[cfg(test)]
mod tests {
    use super::*;
    fn account(id: &str, network: &str) -> Account {
        Account {
            id: id.into(),
            customer_id: "business".into(),
            network: network.into(),
            display_name: network.into(),
            external_id: "123".into(),
            needs_reauth: false,
            expires_at: None,
        }
    }
    fn brief() -> Brief {
        Brief {
            content: "A real update about our business".into(),
            account_ids: vec!["fb".into(), "ig".into(), "tt".into()],
            link: "https://example.com/book".into(),
            hashtags: "#One #one #two #three #four #five #six".into(),
            media: vec!["https://example.com/image.jpg".into()],
            video: None,
        }
    }
    #[test]
    fn versions_are_separate_and_missing_video_blocks_tiktok() {
        let result = compose(
            &brief(),
            &[
                account("fb", "facebook"),
                account("ig", "instagram"),
                account("tt", "tiktok"),
            ],
            &Rules::default(),
        )
        .unwrap();
        assert_eq!(result.len(), 3);
        assert!(result[0].errors.is_empty());
        assert!(!result[1].warnings.is_empty());
        assert!(result[2].errors.iter().any(|e| e.contains("video")));
    }
    #[test]
    fn cross_tenant_and_removed_platforms_fail_closed() {
        let mut b = brief();
        b.account_ids = vec!["other".into()];
        assert!(compose(&b, &[account("fb", "facebook")], &Rules::default()).is_err());
        b.account_ids = vec!["m".into()];
        assert!(compose(&b, &[account("m", "mastodon")], &Rules::default()).is_err());
    }
    #[test]
    fn shortening_is_unicode_safe_and_disclosed() {
        let mut b = brief();
        b.content = "😀 business facts ".repeat(180);
        b.account_ids = vec!["gb".into()];
        let v = compose(&b, &[account("gb", "google_business")], &Rules::default()).unwrap();
        assert!(v[0].length <= 1500);
        assert!(v[0].warnings.iter().any(|s| s.contains("shortened")));
    }
    #[test]
    fn full_text_is_never_published_from_preview() {
        let mut b = brief();
        b.media = vec!["http://localhost/private".into()];
        assert!(compose(&b, &[account("fb", "facebook")], &Rules::default()).is_err());
    }
}
