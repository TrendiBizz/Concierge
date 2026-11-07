//! Per-customer guardrails for social posts: platform limits, verified facts, forbidden phrases, warnings.
//! This is SocialSync's core idea, ported to Rust. Errors block a post from going for approval; warnings do not.
use regex::{Regex, RegexBuilder};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PlatformRule {
    pub label: String,
    pub limit: usize,
    #[serde(default)]
    pub max_media: Option<usize>,
    #[serde(default)]
    pub requires_media: bool,
    #[serde(default)]
    pub max_hashtags: Option<usize>,
    #[serde(default)]
    pub links_clickable: Option<bool>,
    /// Some networks (X) count any link as a fixed length.
    #[serde(default)]
    pub link_length: Option<usize>,
}

/// A fact the owner has verified. A claim that matches `claim_regex` but whose first capture
/// group differs from `value` is an error ("25 years" when the owner verified "10").
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Fact {
    pub key: String,
    pub value: Value,
    pub claim_regex: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct WarningRule {
    pub id: String,
    pub pattern: String,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Rules {
    #[serde(default = "default_platforms")]
    pub platforms: BTreeMap<String, PlatformRule>,
    #[serde(default)]
    pub facts: Vec<Fact>,
    #[serde(default)]
    pub forbidden_phrases: Vec<String>,
    #[serde(default)]
    pub warnings: Vec<WarningRule>,
}

impl Default for Rules {
    fn default() -> Self {
        Rules {
            platforms: default_platforms(),
            facts: vec![],
            forbidden_phrases: vec![],
            warnings: vec![],
        }
    }
}

fn rule(label: &str, limit: usize, max_media: Option<usize>) -> PlatformRule {
    PlatformRule {
        label: label.to_string(),
        limit,
        max_media,
        requires_media: false,
        max_hashtags: None,
        links_clickable: None,
        link_length: None,
    }
}

/// Sensible starting limits. Check them against each network's current documentation.
pub fn default_platforms() -> BTreeMap<String, PlatformRule> {
    let mut m = BTreeMap::new();
    m.insert("linkedin".to_string(), rule("LinkedIn", 3000, Some(9)));
    m.insert("facebook".to_string(), rule("Facebook", 63206, Some(10)));
    m.insert(
        "instagram".to_string(),
        PlatformRule {
            requires_media: true,
            max_hashtags: Some(30),
            links_clickable: Some(false),
            ..rule("Instagram", 2200, Some(10))
        },
    );
    m.insert(
        "x".to_string(),
        PlatformRule {
            link_length: Some(23),
            ..rule("X", 280, Some(4))
        },
    );
    m.insert("threads".to_string(), rule("Threads", 500, Some(20)));
    m.insert("bluesky".to_string(), rule("Bluesky", 300, Some(4)));
    m.insert("mastodon".to_string(), rule("Mastodon", 500, Some(4)));
    m
}

#[derive(Clone, Debug, Default)]
pub struct PostInput {
    pub content: String,
    pub link: String,
    pub hashtags: String,
    /// Network names (linkedin, x, ...) the post is going to.
    pub networks: Vec<String>,
    pub media_count: usize,
}

#[derive(Clone, Debug, Serialize)]
pub struct Issue {
    pub code: String,
    pub network: Option<String>,
    pub message: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct NetworkUse {
    pub label: String,
    pub length: usize,
    pub limit: usize,
    pub over: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct Check {
    pub ok: bool,
    pub errors: Vec<Issue>,
    pub warnings: Vec<Issue>,
    pub networks: BTreeMap<String, NetworkUse>,
}

pub fn count_hashtags(text: &str) -> usize {
    match Regex::new(r"#[\p{L}\p{N}_]+") {
        Ok(re) => re.find_iter(text).count(),
        Err(_) => 0,
    }
}

fn length_for(post: &PostInput, rule: &PlatformRule) -> usize {
    let content = post.content.trim();
    let link = post.link.trim();
    let hashtags = post.hashtags.trim();
    let mut total = content.chars().count();
    if !link.is_empty() {
        let link_len = rule.link_length.unwrap_or_else(|| link.chars().count());
        total += usize::from(total > 0) + link_len;
    }
    if !hashtags.is_empty() {
        total += usize::from(total > 0) + hashtags.chars().count();
    }
    total
}

fn ci_regex(pattern: &str) -> Option<Regex> {
    RegexBuilder::new(pattern)
        .case_insensitive(true)
        .build()
        .ok()
}

fn value_text(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

pub fn check_post(post: &PostInput, rules: &Rules) -> Check {
    let mut errors = Vec::new();
    let mut warnings = Vec::new();
    let mut networks = BTreeMap::new();
    let scan = [
        post.content.as_str(),
        post.link.as_str(),
        post.hashtags.as_str(),
    ]
    .iter()
    .filter(|s| !s.is_empty())
    .cloned()
    .collect::<Vec<_>>()
    .join("\n");

    for name in &post.networks {
        let Some(rule) = rules.platforms.get(name) else {
            errors.push(Issue {
                code: "unknown_network".into(),
                network: Some(name.clone()),
                message: format!("No rules are set for {name}."),
            });
            continue;
        };
        let length = length_for(post, rule);
        let over = length > rule.limit;
        networks.insert(
            name.clone(),
            NetworkUse {
                label: rule.label.clone(),
                length,
                limit: rule.limit,
                over,
            },
        );
        if over {
            errors.push(Issue {
                code: "over_limit".into(),
                network: Some(name.clone()),
                message: format!(
                    "{}: {} characters, the limit is {}.",
                    rule.label, length, rule.limit
                ),
            });
        }
        if rule.requires_media && post.media_count == 0 {
            errors.push(Issue {
                code: "media_required".into(),
                network: Some(name.clone()),
                message: format!("{} needs at least one photo or video.", rule.label),
            });
        }
        if let Some(max) = rule.max_media {
            if post.media_count > max {
                errors.push(Issue {
                    code: "too_much_media".into(),
                    network: Some(name.clone()),
                    message: format!("{} allows at most {} photos or videos.", rule.label, max),
                });
            }
        }
        if let Some(max) = rule.max_hashtags {
            let count = count_hashtags(&format!("{} {}", post.content, post.hashtags));
            if count > max {
                errors.push(Issue {
                    code: "too_many_hashtags".into(),
                    network: Some(name.clone()),
                    message: format!(
                        "{} allows at most {} hashtags (you have {}).",
                        rule.label, max, count
                    ),
                });
            }
        }
        if rule.links_clickable == Some(false) && !post.link.trim().is_empty() {
            warnings.push(Issue {
                code: "link_not_clickable".into(),
                network: Some(name.clone()),
                message: format!(
                    "{} captions do not make links clickable. Put the link in the bio or a story sticker.",
                    rule.label
                ),
            });
        }
    }

    // Verified facts: a claim that contradicts a fact is an error.
    for fact in &rules.facts {
        let Some(re) = ci_regex(&fact.claim_regex) else {
            continue;
        };
        for caps in re.captures_iter(&scan) {
            if let Some(found) = caps.get(1) {
                if found.as_str() != value_text(&fact.value) {
                    errors.push(Issue {
                        code: "unverified_claim".into(),
                        network: None,
                        message: format!(
                            "\"{}\" does not match what the owner verified ({} = {}).",
                            &caps[0],
                            fact.key,
                            value_text(&fact.value)
                        ),
                    });
                }
            }
        }
    }

    let lower = scan.to_lowercase();
    for phrase in &rules.forbidden_phrases {
        if !phrase.is_empty() && lower.contains(&phrase.to_lowercase()) {
            errors.push(Issue {
                code: "forbidden_phrase".into(),
                network: None,
                message: format!(
                    "\"{phrase}\" is on the list of claims this business must never make."
                ),
            });
        }
    }

    // Claims still waiting on the owner: warn but do not block.
    for w in &rules.warnings {
        if let Some(re) = ci_regex(&w.pattern) {
            if re.is_match(&scan) {
                warnings.push(Issue {
                    code: w.id.clone(),
                    network: None,
                    message: w.message.clone(),
                });
            }
        }
    }

    Check {
        ok: errors.is_empty(),
        errors,
        warnings,
        networks,
    }
}
