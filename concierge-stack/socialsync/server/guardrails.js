// Guardrails and per-platform checks for SocialSync posts.
// Pure functions plus a small file-backed rules loader. No dependencies.

import { existsSync, readFileSync, statSync } from 'node:fs';

export const PLATFORM_IDS = ['linkedin', 'facebook', 'instagram', 'twitter'];

// Loads rules.json (and optionally merges Trendi's truth.json). Reloads
// automatically when either file changes, so edits need no restart.
export class RulesStore {
  constructor(rulesPath, truthPath = '') {
    this.rulesPath = rulesPath;
    this.truthPath = truthPath;
    this.cache = null;
    this.stamp = '';
  }

  get() {
    const stamp = [this.rulesPath, this.truthPath]
      .map((p) => (p && existsSync(p) ? statSync(p).mtimeMs : 0))
      .join('|');
    if (!this.cache || stamp !== this.stamp) {
      try {
        this.cache = this.load();
        this.stamp = stamp;
      } catch (err) {
        // Keep the last good rules if the file is mid-edit and invalid.
        if (!this.cache) throw err;
      }
    }
    return this.cache;
  }

  load() {
    const rules = JSON.parse(readFileSync(this.rulesPath, 'utf8'));
    if (this.truthPath && existsSync(this.truthPath)) {
      try {
        const truth = JSON.parse(readFileSync(this.truthPath, 'utf8'));
        const facts = new Map((rules.facts || []).map((f) => [f.key, f]));
        for (const fact of truth.facts || []) facts.set(fact.key, fact);
        rules.facts = [...facts.values()];
        rules.forbidden_phrases = [
          ...new Set([...(rules.forbidden_phrases || []), ...(truth.forbidden_phrases || [])]),
        ];
        rules._truthLoaded = this.truthPath;
      } catch (err) {
        rules._truthError = String(err && err.message ? err.message : err);
      }
    }
    return rules;
  }
}

function clean(value) {
  return typeof value === 'string' ? value.trim() : '';
}

export function countHashtags(text) {
  return (String(text || '').match(/#[\p{L}\p{N}_]+/gu) || []).length;
}

// Characters this post will use on one platform. Some platforms (X) count any
// link as a fixed length regardless of the real URL.
export function lengthFor(post, platformRule) {
  const content = clean(post.content);
  const link = clean(post.link);
  const hashtags = clean(post.hashtags);
  let total = Array.from(content).length;
  if (link) {
    const linkLength = platformRule.linkLength ?? Array.from(link).length;
    total += (total ? 1 : 0) + linkLength;
  }
  if (hashtags) total += (total ? 1 : 0) + Array.from(hashtags).length;
  return total;
}

function compile(pattern, flags) {
  try {
    return new RegExp(pattern, flags);
  } catch {
    return null;
  }
}

// post: { content, link, hashtags, platforms: string[], media_ids: number[] }
// Returns { ok, errors, warnings, platforms } where errors block scheduling.
export function checkPost(post, rules) {
  const errors = [];
  const warnings = [];
  const platformRules = rules.platforms || {};
  const platforms = (Array.isArray(post.platforms) ? post.platforms : []).filter(
    (id) => platformRules[id],
  );
  const mediaCount = Array.isArray(post.media_ids) ? post.media_ids.length : 0;
  const scanText = [post.content, post.link, post.hashtags].filter(Boolean).join('\n');
  const perPlatform = {};

  for (const id of platforms) {
    const rule = platformRules[id];
    const length = lengthFor(post, rule);
    const over = length > rule.limit;
    perPlatform[id] = { label: rule.label, length, limit: rule.limit, over };

    if (over) {
      errors.push({
        code: 'over_limit',
        platform: id,
        message: `${rule.label}: ${length} characters, the limit is ${rule.limit}.`,
      });
    }
    if (rule.requiresMedia && mediaCount === 0) {
      errors.push({
        code: 'media_required',
        platform: id,
        message: `${rule.label} needs at least one photo or video.`,
      });
    }
    if (rule.maxMedia && mediaCount > rule.maxMedia) {
      errors.push({
        code: 'too_much_media',
        platform: id,
        message: `${rule.label} allows at most ${rule.maxMedia} photos or videos.`,
      });
    }
    if (rule.maxHashtags != null) {
      const count = countHashtags(`${post.content || ''} ${post.hashtags || ''}`);
      if (count > rule.maxHashtags) {
        errors.push({
          code: 'too_many_hashtags',
          platform: id,
          message: `${rule.label} allows at most ${rule.maxHashtags} hashtags (you have ${count}).`,
        });
      }
    }
    if (rule.linksClickable === false && clean(post.link)) {
      warnings.push({
        code: 'link_not_clickable',
        platform: id,
        message: `${rule.label} captions do not make links clickable. Put the link in your bio or a story sticker.`,
      });
    }
  }

  // Verified facts: a claim that contradicts a fact is an error.
  for (const fact of rules.facts || []) {
    const re = compile(fact.claim_regex, 'gi');
    if (!re) continue;
    for (const match of scanText.matchAll(re)) {
      if (match[1] !== undefined && String(match[1]) !== String(fact.value)) {
        errors.push({
          code: 'unverified_claim',
          fact: fact.key,
          message: `"${match[0]}" does not match what the owner verified (${fact.key} = ${fact.value}).`,
        });
      }
    }
  }

  const lower = scanText.toLowerCase();
  for (const phrase of rules.forbidden_phrases || []) {
    if (phrase && lower.includes(String(phrase).toLowerCase())) {
      errors.push({
        code: 'forbidden_phrase',
        message: `"${phrase}" is on the list of claims Pukeko must never make.`,
      });
    }
  }

  // Claims still waiting on the owner: warn, but do not block.
  for (const rule of rules.warnings || []) {
    const re = compile(rule.pattern, 'i');
    if (!re) continue;
    const match = re.exec(scanText);
    if (match) {
      warnings.push({ code: rule.id, message: rule.message, match: match[0] });
    }
  }

  return { ok: errors.length === 0, errors, warnings, platforms: perPlatform };
}
