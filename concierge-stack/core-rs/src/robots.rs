//! `urllib.robotparser.RobotFileParser` as shipped with CPython 3.13.18 (the RFC 9309 implementation): grouping,
//! longest-match rule selection with Allow winning ties, `*` and `$` patterns (atomic lazy groups, like the original) and
//! percent-normalisation. Only the allow/deny decision is ported; crawl-delay and request-rate never affect it.
use crate::pyurl::{urlsplit, urlunsplit, Fail, Split};
use crate::{py_splitlines, py_strip};
use fancy_regex::Regex;

fn hex(b: u8) -> Option<u8> {
    (b as char).to_digit(16).map(|d| d as u8)
}

/// `quote(unquote(s, errors="surrogateescape"), errors="surrogateescape")` with the default safe set (`/`).
pub fn normalize(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut raw: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (hex(bytes[i + 1]), hex(bytes[i + 2])) {
                raw.push(h * 16 + l);
                i += 3;
                continue;
            }
        }
        raw.push(bytes[i]);
        i += 1;
    }
    let mut out = String::with_capacity(raw.len());
    for b in raw {
        if b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'-' | b'~' | b'/') {
            out.push(b as char);
        } else {
            out.push_str(&format!("%{b:02X}"));
        }
    }
    out
}

/// Apply `f` to each maximal run of characters not in `keep` (Python `re.sub(r"[^...]+", ...)`).
fn map_runs(s: &str, keep: &[char], f: impl Fn(&str) -> String) -> String {
    let mut out = String::new();
    let mut run = String::new();
    for c in s.chars() {
        if keep.contains(&c) {
            if !run.is_empty() {
                out.push_str(&f(&run));
                run.clear();
            }
            out.push(c);
        } else {
            run.push(c);
        }
    }
    if !run.is_empty() {
        out.push_str(&f(&run));
    }
    out
}

pub fn normalize_uri(path: &str) -> String {
    match path.split_once('?') {
        None => normalize(path),
        Some((p, q)) => format!("{}?{}", normalize(p), map_runs(q, &['=', '&'], normalize)),
    }
}

fn normalize_pattern(path: &str) -> String {
    match path.split_once('?') {
        None => map_runs(path, &['*', '$'], normalize),
        Some((p, q)) => format!(
            "{}?{}",
            map_runs(p, &['*', '$'], normalize),
            map_runs(q, &['=', '&', '*', '$'], normalize)
        ),
    }
}

#[derive(Clone)]
struct RuleLine {
    path: String,
    allowance: bool,
    fullmatch: bool,
    matcher: Option<Regex>,
}

impl RuleLine {
    /// `Err(())` is the ValueError for a `$` that is not at the end: the rule is skipped.
    fn new(path: &str, mut allowance: bool) -> Result<RuleLine, ()> {
        if path.is_empty() && !allowance {
            allowance = true;
        }
        // re.sub(r"[*]{2,}", "*") then re.sub(r"[$][$*]+", "$")
        let mut a = String::new();
        let mut stars = 0;
        for c in path.chars().chain(std::iter::once('\0')) {
            if c == '*' {
                stars += 1;
                continue;
            }
            if stars > 0 {
                a.push('*');
                stars = 0;
            }
            if c != '\0' {
                a.push(c);
            }
        }
        let mut b = String::new();
        let mut chars = a.chars().peekable();
        while let Some(c) = chars.next() {
            b.push(c);
            if c == '$' {
                while matches!(chars.peek(), Some('$') | Some('*')) {
                    chars.next();
                }
            }
        }
        let normalized = normalize_pattern(&b);
        let fullmatch = normalized.ends_with('$');
        let path = normalized.trim_end_matches('$').to_string();
        if path.contains('$') {
            return Err(());
        }
        let matcher = if path.contains('*') {
            let parts: Vec<String> = path
                .split('*')
                .map(fancy_regex::escape)
                .map(|c| c.into_owned())
                .collect();
            let mut pat = String::from("(?s)\\A");
            pat.push_str(&parts[0]);
            for p in &parts[1..parts.len() - 1] {
                pat.push_str(&format!("(?>.*?{p})"));
            }
            pat.push_str(&format!(".*{}", parts[parts.len() - 1]));
            if fullmatch {
                pat.push_str("\\z");
            }
            Some(Regex::new(&pat).map_err(|_| ())?)
        } else {
            None
        };
        Ok(RuleLine {
            path,
            allowance,
            fullmatch,
            matcher,
        })
    }

    /// Matching length plus one, or 0 when the rule does not apply.
    fn applies_to(&self, filename: &str) -> usize {
        if let Some(re) = &self.matcher {
            if let Ok(Some(m)) = re.find(filename) {
                return m.end() + 1;
            }
            return 0;
        }
        if self.fullmatch {
            if filename == self.path {
                return self.path.len() + 1;
            }
        } else if filename.starts_with(&self.path) {
            return self.path.len() + 1;
        }
        0
    }
}

#[derive(Clone, Default)]
struct Entry {
    useragents: Vec<String>,
    rulelines: Vec<RuleLine>,
}

impl Entry {
    fn applies_to(&self, useragent: &str) -> bool {
        let token = useragent.split('/').next().unwrap_or("").to_lowercase();
        self.useragents
            .iter()
            .any(|a| a != "*" && token.contains(&a.to_lowercase()))
    }
    fn allowance(&self, filename: &str) -> bool {
        let mut best: i64 = -1;
        let mut allowance = true;
        for line in &self.rulelines {
            let m = line.applies_to(filename) as i64;
            if m != 0 {
                if m > best {
                    best = m;
                    allowance = line.allowance;
                } else if m == best && !allowance {
                    allowance = line.allowance;
                }
            }
        }
        allowance
    }
}

fn merge(e1: &Entry, e2: &Entry) -> Entry {
    Entry {
        useragents: e1
            .useragents
            .iter()
            .filter(|a| e2.useragents.contains(a))
            .cloned()
            .collect(),
        rulelines: e1.rulelines.iter().chain(&e2.rulelines).cloned().collect(),
    }
}

pub struct Robots {
    /// Insertion-ordered, like the dict it mirrors.
    groups: Vec<(String, Entry)>,
    /// `Robots(None)`: no usable robots.txt, everything allowed.
    empty: bool,
}

impl Robots {
    pub fn none() -> Robots {
        Robots {
            groups: vec![],
            empty: true,
        }
    }

    /// `Robots(text)`: an empty text means no parser (everything allowed).
    pub fn new(text: Option<&str>) -> Robots {
        match text {
            Some(t) if !t.is_empty() => Robots::parse(&py_splitlines(t)),
            _ => Robots::none(),
        }
    }

    fn add_entry(groups: &mut Vec<(String, Entry)>, entry: &Entry) {
        for agent in &entry.useragents {
            let key = agent.to_lowercase();
            match groups.iter_mut().find(|(k, _)| *k == key) {
                None => groups.push((key, entry.clone())),
                Some((_, existing)) => *existing = merge(existing, entry),
            }
        }
    }

    fn parse(lines: &[&str]) -> Robots {
        let mut groups: Vec<(String, Entry)> = Vec::new();
        let mut state = 0;
        let mut entry = Entry::default();
        for line in lines {
            let line = match line.find('#') {
                Some(i) => &line[..i],
                None => line,
            };
            let line = py_strip(line);
            if line.is_empty() {
                continue;
            }
            let Some((key, value)) = line.split_once(':') else {
                continue;
            };
            let key = py_strip(key).to_lowercase();
            let value = py_strip(value);
            match key.as_str() {
                "user-agent" => {
                    if state == 2 {
                        Robots::add_entry(&mut groups, &entry);
                        entry = Entry::default();
                    }
                    entry.useragents.push(value.to_string());
                    state = 1;
                }
                "disallow" | "allow" => {
                    if state != 0 {
                        state = 2;
                        if let Ok(rule) = RuleLine::new(value, key == "allow") {
                            entry.rulelines.push(rule);
                        }
                    }
                }
                "crawl-delay" | "request-rate" if state != 0 => state = 2,
                _ => {}
            }
        }
        if state != 0 {
            Robots::add_entry(&mut groups, &entry);
        }
        Robots {
            groups,
            empty: false,
        }
    }

    fn find_entry(&self, useragent: &str) -> Option<&Entry> {
        let lower = useragent.to_lowercase();
        if let Some((_, e)) = self.groups.iter().find(|(k, _)| *k == lower) {
            return Some(e);
        }
        for (_, e) in &self.groups {
            if e.applies_to(useragent) {
                return Some(e);
            }
        }
        self.groups.iter().find(|(k, _)| k == "*").map(|(_, e)| e)
    }

    pub fn can_fetch(&self, useragent: &str, url: &str) -> Result<bool, Fail> {
        if self.empty {
            return Ok(true);
        }
        let s = urlsplit(url, "")?;
        let rel = urlunsplit(&Split {
            scheme: String::new(),
            netloc: String::new(),
            path: s.path,
            query: s.query,
            fragment: s.fragment,
        });
        let mut rel = normalize_uri(&rel);
        if rel.is_empty() {
            rel = "/".into();
        }
        if rel == "/robots.txt" {
            return Ok(true);
        }
        Ok(match self.find_entry(useragent) {
            None => true,
            Some(e) => e.allowance(&rel),
        })
    }
}
