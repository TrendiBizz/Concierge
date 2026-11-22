"""Per-customer guardrails and multi-network composer previews for Concierge Social.

Errors block a post from being submitted for approval or published; warnings inform the owner.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .config import ALL_NETWORKS

_UPLOAD_RE = re.compile(r"^upload:[A-Za-z0-9_-]{20,128}$")
_HASHTAG_RE = re.compile(r"#[\w]+", re.UNICODE)


@dataclass(frozen=True)
class PlatformRule:
    label: str
    limit: int
    max_media: int | None = None
    requires_media: bool = False
    max_hashtags: int | None = None
    links_clickable: bool | None = None
    link_length: int | None = None


def default_platforms() -> dict[str, PlatformRule]:
    return {
        "linkedin": PlatformRule("LinkedIn", 3000, max_media=9),
        "linkedin_organization": PlatformRule("LinkedIn Company Page", 3000, max_media=9),
        "tiktok": PlatformRule("TikTok", 2200, max_media=1, requires_media=True, max_hashtags=5),
        "google_business": PlatformRule("Google Business Profile", 1500, max_media=1),
        "facebook": PlatformRule("Facebook", 63206, max_media=10),
        "instagram": PlatformRule(
            "Instagram", 2200, max_media=10, requires_media=True, max_hashtags=30, links_clickable=False
        ),
        "x": PlatformRule("X", 280, max_media=4, link_length=23),
    }


def x_length(text: str) -> int:
    """Conservative X weighted length: Latin 1, other Unicode 2, valid URLs 23."""
    total = 0
    for part in re.findall(r"\S+\s*|\s+", text):
        word = part.rstrip()
        space = len(part) - len(word)
        weight = 0
        for ch in word:
            cp = ord(ch)
            if cp <= 0x10FF or (0x2000 <= cp <= 0x200D) or (0x2010 <= cp <= 0x201F) or (0x2032 <= cp <= 0x2037):
                weight += 1
            else:
                weight += 2
        if word.startswith("https://") or word.startswith("http://"):
            url = word.rstrip(".,!?;:)]}\"'")
            parsed = urlsplit(url)
            if parsed.hostname:
                total += 23 + (len(word) - len(url)) + space
                continue
        total += weight + space
    return total


def count_hashtags(text: str) -> int:
    return len(_HASHTAG_RE.findall(text or ""))


def _length_for(content: str, link: str, hashtags: str, rule: PlatformRule) -> int:
    c = (content or "").strip()
    lk = (link or "").strip()
    ht = (hashtags or "").strip()
    if rule.link_length is not None:
        parts = [p for p in (c, lk, ht) if p]
        return x_length("\n".join(parts))
    total = len(c)
    if lk:
        total += (1 if total else 0) + len(lk)
    if ht:
        total += (1 if total else 0) + len(ht)
    return total


def check_post(
    *,
    content: str,
    link: str = "",
    hashtags: str = "",
    networks: list[str],
    media_count: int = 0,
    rules: dict | None = None,
) -> dict:
    rules = rules or {}
    platforms = default_platforms()
    errors: list[dict] = []
    warnings: list[dict] = []
    net_summary: dict[str, dict] = {}

    if not (content or "").strip():
        errors.append({"code": "empty_content", "network": None, "message": "Post content cannot be empty"})

    full_text = " ".join(p for p in (content, link, hashtags) if p)
    lowered = full_text.lower()

    for phrase in rules.get("forbidden_phrases") or []:
        if isinstance(phrase, str) and phrase.strip() and phrase.strip().lower() in lowered:
            errors.append({
                "code": "forbidden_phrase",
                "network": None,
                "message": f"Forbidden phrase found: {phrase.strip()}",
            })

    for fact in rules.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        pattern = str(fact.get("claim_regex") or "")
        expected = str(fact.get("value") or "")
        key = str(fact.get("key") or "fact")
        if pattern:
            try:
                for m in re.finditer(pattern, full_text, re.IGNORECASE):
                    if m.groups() and m.group(1).strip().lower() != expected.strip().lower():
                        errors.append({
                            "code": "fact_mismatch",
                            "network": None,
                            "message": f"Claim '{m.group(0)}' conflicts with verified {key} ({expected})",
                        })
            except re.error:
                pass

    for warn in rules.get("warnings") or []:
        if not isinstance(warn, dict):
            continue
        pattern = str(warn.get("pattern") or "")
        if pattern:
            try:
                if re.search(pattern, full_text, re.IGNORECASE):
                    warnings.append({
                        "code": str(warn.get("id") or "warning"),
                        "network": None,
                        "message": str(warn.get("message") or "Review this post before publishing"),
                    })
            except re.error:
                pass

    tag_count = count_hashtags(f"{content} {hashtags}")
    for net in networks:
        rule = platforms.get(net)
        if not rule:
            errors.append({"code": "unsupported_network", "network": net, "message": f"Unsupported network: {net}"})
            continue
        length = _length_for(content, link, hashtags, rule)
        over = length > rule.limit
        net_summary[net] = {"label": rule.label, "length": length, "limit": rule.limit, "over": over}
        if over:
            errors.append({
                "code": "too_long",
                "network": net,
                "message": f"{rule.label} post is {length} characters (limit {rule.limit})",
            })
        if rule.requires_media and media_count == 0:
            errors.append({
                "code": "media_required",
                "network": net,
                "message": f"{rule.label} requires at least one image or video",
            })
        if rule.max_media is not None and media_count > rule.max_media:
            errors.append({
                "code": "too_much_media",
                "network": net,
                "message": f"{rule.label} allows at most {rule.max_media} media item(s)",
            })
        if rule.max_hashtags is not None and tag_count > rule.max_hashtags:
            warnings.append({
                "code": "too_many_hashtags",
                "network": net,
                "message": f"{rule.label} recommends at most {rule.max_hashtags} hashtags",
            })
        if rule.links_clickable is False and (link or "").strip():
            warnings.append({
                "code": "link_not_clickable",
                "network": net,
                "message": f"{rule.label} caption links are not clickable",
            })

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "networks": net_summary,
    }


def _valid_media_or_link(url: str) -> bool:
    if not url:
        return True
    if _UPLOAD_RE.fullmatch(url):
        return True
    if len(url) > 2048:
        return False
    parsed = urlsplit(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def _shorten(text: str, limit: int, counter=len) -> tuple[str, bool]:
    if counter(text) <= limit:
        return text, False
    room = max(0, limit - counter("…"))
    out = ""
    for word in text.split():
        cand = word if not out else f"{out} {word}"
        if counter(cand) > room:
            break
        out = cand
    if not out:
        for ch in text:
            if counter(out + ch) > room:
                break
            out += ch
    return out + "…", True


def compose_variants(brief: dict, accounts: list[dict], rules: dict | None = None) -> list[dict]:
    content = str(brief.get("content") or "")
    account_ids = list(brief.get("account_ids") or [])
    link = str(brief.get("link") or "").strip()
    hashtags = str(brief.get("hashtags") or "").strip()
    media = list(brief.get("media") or [])
    video = brief.get("video")

    if not content.strip() or len(content) > 10000 or not (1 <= len(account_ids) <= 10) or len(media) > 10:
        raise ValueError("Enter a post and select between one and ten accounts")
    if len(set(account_ids)) != len(account_ids):
        raise ValueError("An account was selected more than once")
    for u in [*media, *([video] if video else []), link]:
        if u and not _valid_media_or_link(str(u)):
            raise ValueError("Use valid HTTPS links and media URLs")

    by_id = {a["id"]: a for a in accounts}
    platforms = default_platforms()
    variants: list[dict] = []

    for aid in account_ids:
        acct = by_id.get(aid)
        if not acct:
            raise ValueError("Selected account is not available for this business")
        net = acct["network"]
        if net not in ALL_NETWORKS:
            raise ValueError("This platform is not offered in Concierge")
        rule = platforms[net]
        warnings: list[str] = []
        errors: list[str] = []
        if acct.get("needs_reauth"):
            errors.append("Reconnect this account before scheduling")

        max_tags = 0 if net == "google_business" else (3 if net in ("linkedin", "linkedin_organization") else 5)
        seen: set[str] = set()
        raw_tags = [t for t in hashtags.split() if t.startswith("#") and not (t.lower() in seen or seen.add(t.lower()))]
        if len(raw_tags) > max_tags:
            warnings.append(f"Hashtags reduced to {max_tags} for this destination; review before approval")
        chosen_tags = " ".join(raw_tags[:max_tags])

        if net == "instagram" and link:
            warnings.append("Instagram caption links are not clickable; add the destination to your profile if needed")

        if net == "tiktok":
            if video:
                if not str(video).startswith("upload:"):
                    errors.append("Upload the TikTok video for server duration verification")
                chosen_media = [str(video)]
            else:
                errors.append("Add a video for TikTok")
                chosen_media = []
        elif net == "google_business":
            if not media and video:
                warnings.append("Google Business uses a still image from your video; review it before approval")
            chosen_media = [str(m) for m in media[:1]]
        else:
            if len(media) > 1:
                warnings.append("The first image is selected for this destination")
            first = media[0] if media else video
            chosen_media = [str(first)] if first else []
            if net == "instagram" and not chosen_media:
                errors.append("Add an image or video for Instagram")

        counter = x_length if net == "x" else len
        overhead = 0
        if link:
            overhead += 1 + (23 if net == "x" else len(link))
        if chosen_tags:
            overhead += 1 + counter(chosen_tags)
        body_budget = max(1, rule.limit - overhead)
        adapted_content, was_shortened = _shorten(content.strip(), body_budget, counter)
        if was_shortened:
            warnings.append(f"Text shortened to fit {rule.label}'s {rule.limit}-character limit; review before approval")

        chk = check_post(
            content=adapted_content,
            link=link,
            hashtags=chosen_tags,
            networks=[net],
            media_count=len(chosen_media),
            rules=rules,
        )
        for item in chk["errors"]:
            if item["message"] not in errors:
                errors.append(item["message"])
        for item in chk["warnings"]:
            if item["message"] not in warnings:
                warnings.append(item["message"])

        length = _length_for(adapted_content, link, chosen_tags, rule)
        variants.append({
            "account_id": aid,
            "account_name": acct.get("display_name") or rule.label,
            "network": net,
            "content": adapted_content,
            "link": link,
            "hashtags": chosen_tags,
            "media": chosen_media,
            "video": video if net == "tiktok" else None,
            "warnings": warnings,
            "errors": errors,
            "length": length,
            "limit": rule.limit,
        })

    return variants
