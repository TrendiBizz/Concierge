//! Port of the decision logic in `crawler.py`: URL normalisation, link extraction through CPython 3.13.18's
//! `html.parser` rules, sitemap reading, robots.txt use and the crawl loop. Network transfer (`Net`) and article text
//! extraction (`extract`, trafilatura) are supplied by the caller; everything that decides *what* is fetched is here.
use crate::py_strip;
use crate::pyurl::{hostname, urldefrag, urljoin, urlsplit, urlunsplit, Fail, Split};
use crate::robots::Robots;
use fancy_regex::Regex;
use std::collections::{HashMap, HashSet, VecDeque};
use std::sync::OnceLock;

pub const USER_AGENT: &str = "ConciergeBot/1.0 (indexing at the site owner's request)";
pub const MAX_HTML_BYTES: usize = 3_000_000;
const SKIP_EXTENSIONS: [&str; 26] = [
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".zip", ".gz", ".mp4",
    ".mp3", ".mov", ".avi", ".css", ".js", ".json", ".xml", ".woff", ".woff2", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx",
];

pub fn host_of(url: &str) -> Result<String, Fail> {
    let s = urlsplit(url, "")?;
    let host = hostname(&s.netloc).unwrap_or_default().to_lowercase();
    Ok(host.strip_prefix("www.").map(String::from).unwrap_or(host))
}

/// Absolute http(s) URL without fragment or query string, or `None` if not crawlable.
pub fn normalize(url: &str, base: Option<&str>) -> Result<Option<String>, Fail> {
    let joined;
    let url = match base {
        Some(b) if !b.is_empty() => {
            joined = urljoin(b, url)?;
            joined.as_str()
        }
        _ => url,
    };
    let url = urldefrag(py_strip(url))?;
    let parts = urlsplit(&url, "")?;
    if !matches!(parts.scheme.as_str(), "http" | "https") || parts.netloc.is_empty() {
        return Ok(None);
    }
    let path = if parts.path.is_empty() {
        "/".to_string()
    } else {
        parts.path.clone()
    };
    let lower = path.to_lowercase();
    if SKIP_EXTENSIONS.iter().any(|e| lower.ends_with(e)) {
        return Ok(None);
    }
    Ok(Some(urlunsplit(&Split {
        scheme: parts.scheme,
        netloc: parts.netloc.to_lowercase(),
        path,
        query: String::new(),
        fragment: String::new(),
    })))
}

// ---- HTML link extraction: html.parser (convert_charrefs=True), one feed(), never close()d -----------------------

fn re(cell: &'static OnceLock<Regex>, pattern: &str) -> &'static Regex {
    cell.get_or_init(|| Regex::new(pattern).unwrap())
}

fn tagfind() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    re(&R, r"\A([a-zA-Z][^\t\n\r\f />]*)(?:[\t\n\r\f ]|/(?!>))*")
}
fn locatetagend() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    re(
        &R,
        r#"\A[a-zA-Z][^\t\n\r\f />]*[\t\n\r\f /]*(?:(?<=['"\t\n\r\f /])[^\t\n\r\f />][^\t\n\r\f /=>]*(?:[\t\n\r\f ]*=[\t\n\r\f ]*(?:'[^']*'|"[^"]*"|(?!['"])[^>\t\n\r\f ]*))?[\t\n\r\f /]*)*>?"#,
    )
}
/// Anchored after one previous character so the leading lookbehind can see it.
fn attrfind() -> &'static Regex {
    static R: OnceLock<Regex> = OnceLock::new();
    re(
        &R,
        r#"\A(?s:.)((?<=['"\t\n\r\f /])[^\t\n\r\f />][^\t\n\r\f /=>]*)([\t\n\r\f ]*=[\t\n\r\f ]*('[^']*'|"[^"]*"|(?!['"])[^>\t\n\r\f ]*))?(?:[\t\n\r\f ]|/(?!>))*"#,
    )
}

#[derive(Debug, PartialEq, Eq)]
pub struct Tag {
    pub name: String,
    pub attrs: Vec<(String, Option<String>)>,
}

struct Tables {
    entities: HashMap<String, String>,
    invalid_charrefs: HashMap<u32, String>,
    invalid_codepoints: HashSet<u32>,
}

fn tables() -> &'static Tables {
    static T: OnceLock<Tables> = OnceLock::new();
    T.get_or_init(|| {
        let v: serde_json::Value = serde_json::from_str(include_str!("html_tables.json")).unwrap();
        Tables {
            entities: v["entities"]
                .as_object()
                .unwrap()
                .iter()
                .map(|(k, x)| (k.clone(), x.as_str().unwrap().to_string()))
                .collect(),
            invalid_charrefs: v["invalid_charrefs"]
                .as_object()
                .unwrap()
                .iter()
                .map(|(k, x)| (k.parse().unwrap(), x.as_str().unwrap().to_string()))
                .collect(),
            invalid_codepoints: v["invalid_codepoints"]
                .as_array()
                .unwrap()
                .iter()
                .map(|x| x.as_u64().unwrap() as u32)
                .collect(),
        }
    })
}

/// `html.parser._unescape_attrvalue`.
pub fn unescape_attrvalue(s: &str) -> String {
    static R: OnceLock<regex::Regex> = OnceLock::new();
    let r = R.get_or_init(|| {
        regex::Regex::new(r"&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*)[;=]?").unwrap()
    });
    let t = tables();
    r.replace_all(s, |c: &regex::Captures| {
        let whole = c.get(0).unwrap().as_str();
        if let Some(num) = whole.strip_prefix("&#") {
            let (digits, radix) = match num.strip_prefix(['x', 'X']) {
                Some(h) => (h, 16),
                None => (num, 10),
            };
            let digits = digits.trim_end_matches([';', '=']);
            let n = u32::from_str_radix(digits, radix).unwrap_or(u32::MAX);
            let rep = if let Some(r) = t.invalid_charrefs.get(&n) {
                r.clone()
            } else if (0xD800..=0xDFFF).contains(&n) || n > 0x10FFFF {
                "\u{fffd}".to_string()
            } else if t.invalid_codepoints.contains(&n) {
                String::new()
            } else {
                char::from_u32(n).map(String::from).unwrap_or_default()
            };
            return if whole.ends_with('=') {
                format!("{rep}=")
            } else {
                rep
            };
        }
        if !whole.ends_with('=') {
            if let Some(v) = t.entities.get(&whole[1..]) {
                return v.clone();
            }
        }
        whole.to_string()
    })
    .into_owned()
}

/// Start tags in document order, with CPython's tolerance for broken markup. `Err` only if a pattern exceeded the
/// backtracking limit (reported, never guessed).
pub fn start_tags(html: &str) -> Result<Vec<Tag>, Fail> {
    let n = html.len();
    let mut tags = Vec::new();
    let mut i = 0;
    let mut cdata: Option<String> = None;
    let bad = |_| Fail::Unsupported("regex backtracking limit");
    while i < n {
        let j = match &cdata {
            None => match html[i..].find('<') {
                Some(p) => i + p,
                None => break,
            },
            Some(name) if name == "plaintext" => n,
            Some(name) => match find_cdata_end(html, i, name) {
                Some(p) => p,
                None => break,
            },
        };
        i = j;
        if i == n {
            break;
        }
        let rest = &html[i..];
        let b = rest.as_bytes();
        let k: isize = if b.len() >= 2 && b[1].is_ascii_alphabetic() {
            // parse_starttag
            let Some(m) = locatetagend().find(&html[i + 1..]).map_err(bad)? else {
                unreachable!()
            };
            let endpos = i + 1 + m.end();
            if html.as_bytes()[endpos - 1] != b'>' {
                -1
            } else {
                let tm = tagfind().captures(&html[i + 1..]).map_err(bad)?.unwrap();
                let name = tm.get(1).unwrap().as_str().to_lowercase();
                let mut k = i + 1 + tm.get(0).unwrap().end();
                let mut attrs = Vec::new();
                while k < endpos {
                    // start one character earlier so the lookbehind has something to look at
                    let prev = html[..k]
                        .char_indices()
                        .next_back()
                        .map(|(p, _)| p)
                        .unwrap_or(0);
                    let Some(m) = attrfind().captures(&html[prev..]).map_err(bad)? else {
                        break;
                    };
                    let name = m.get(1).unwrap().as_str().to_lowercase();
                    let rest = m.get(2).map(|x| x.as_str()).unwrap_or("");
                    let mut value = if rest.is_empty() {
                        None
                    } else {
                        let v = m.get(3).unwrap().as_str();
                        let q = v.as_bytes().first().copied();
                        if v.len() >= 2
                            && (q == Some(b'\'') || q == Some(b'"'))
                            && v.as_bytes()[v.len() - 1] == q.unwrap()
                        {
                            Some(v[1..v.len() - 1].to_string())
                        } else if v.len() == 1 && (q == Some(b'\'') || q == Some(b'"')) {
                            // Python: v[:1] == "'" == v[-1:] holds for a lone quote, and v[1:-1] is empty
                            Some(String::new())
                        } else {
                            Some(v.to_string())
                        }
                    };
                    if let Some(v) = &value {
                        if !v.is_empty() {
                            value = Some(unescape_attrvalue(v));
                        }
                    }
                    attrs.push((name, value));
                    k = prev + m.get(0).unwrap().end();
                }
                let end = py_strip(&html[k.min(endpos)..endpos]);
                if end != ">" && end != "/>" {
                    // junk after the attributes: treated as text
                } else {
                    let selfclosing = end.ends_with("/>");
                    tags.push(Tag {
                        name: name.clone(),
                        attrs,
                    });
                    if !selfclosing
                        && matches!(
                            name.as_str(),
                            "script"
                                | "style"
                                | "xmp"
                                | "iframe"
                                | "noembed"
                                | "noframes"
                                | "plaintext"
                                | "textarea"
                                | "title"
                        )
                    {
                        cdata = Some(name);
                    }
                }
                endpos as isize
            }
        } else if rest.starts_with("</") {
            parse_endtag(html, i, &mut cdata)?
        } else if rest.starts_with("<!--") {
            // an empty comment is closed by the first ">" or "->", before any later "-->" or "--!>"
            let after = &html[i + 4..];
            if after.starts_with('>') {
                (i + 5) as isize
            } else if after.starts_with("->") {
                (i + 6) as isize
            } else {
                match find_comment_close(after) {
                    Some(end) => (i + 4 + end) as isize,
                    None => -1,
                }
            }
        } else if rest.starts_with("<?") {
            match html[i + 2..].find('>') {
                Some(p) => (i + 2 + p + 1) as isize,
                None => -1,
            }
        } else if rest.starts_with("<!") {
            if rest.starts_with("<![CDATA[") {
                match html[i + 9..].find("]]>") {
                    Some(p) => (i + 9 + p + 3) as isize,
                    None => -1,
                }
            } else if rest.len() >= 9 && rest.as_bytes()[..9].eq_ignore_ascii_case(b"<!doctype") {
                match html[i + 9..].find('>') {
                    Some(p) => (i + 9 + p + 1) as isize,
                    None => -1,
                }
            } else {
                match html[i + 2..].find('>') {
                    Some(p) => (i + 2 + p + 1) as isize,
                    None => -1,
                }
            }
        } else if i + 1 < n {
            (i + 1) as isize
        } else {
            break;
        };
        if k < 0 {
            break; // incomplete markup: the parser waits for more data that never comes (no close())
        }
        i = k as usize;
    }
    Ok(tags)
}

/// End of the first `--!?>` at or after the start of `s`.
fn find_comment_close(s: &str) -> Option<usize> {
    let b = s.as_bytes();
    (0..b.len().saturating_sub(2)).find_map(|p| {
        if b[p] == b'-' && b[p + 1] == b'-' {
            if b[p + 2] == b'>' {
                return Some(p + 3);
            }
            if b[p + 2] == b'!' && p + 3 < b.len() && b[p + 3] == b'>' {
                return Some(p + 4);
            }
        }
        None
    })
}

/// Start of `</name` followed by one of `\t\n\r\f />`, ASCII case-insensitive, at or after `from`.
fn find_cdata_end(html: &str, from: usize, name: &str) -> Option<usize> {
    let b = html.as_bytes();
    let nb = name.as_bytes();
    let mut p = from;
    while p + 2 + nb.len() < b.len() {
        if b[p] == b'<'
            && b[p + 1] == b'/'
            && b[p + 2..p + 2 + nb.len()].eq_ignore_ascii_case(nb)
            && matches!(
                b[p + 2 + nb.len()],
                b'\t' | b'\n' | b'\r' | 0x0c | b' ' | b'/' | b'>'
            )
        {
            return Some(p);
        }
        p += 1;
    }
    None
}

fn parse_endtag(html: &str, i: usize, cdata: &mut Option<String>) -> Result<isize, Fail> {
    let Some(gt) = html[i + 2..].find('>') else {
        return Ok(-1);
    };
    let b = html.as_bytes();
    if !(i + 2 < b.len() && b[i + 2].is_ascii_alphabetic()) {
        if b.get(i + 2) == Some(&b'>') {
            return Ok((i + 3) as isize);
        }
        return Ok((i + 2 + gt + 1) as isize); // bogus comment
    }
    let m = locatetagend()
        .find(&html[i + 2..])
        .map_err(|_| Fail::Unsupported("regex backtracking limit"))?
        .unwrap();
    let j = i + 2 + m.end();
    if b[j - 1] != b'>' {
        return Ok(-1);
    }
    *cdata = None;
    Ok(j as isize)
}

/// `extract_links(html, base_url)`: normalised links in document order. `Err(Value)` if `normalize` raises.
pub fn extract_links(html: &str, base_url: &str) -> Result<Vec<String>, Fail> {
    let mut out = Vec::new();
    for tag in start_tags(html)? {
        if tag.name == "a" {
            for (name, value) in &tag.attrs {
                if name == "href" {
                    if let Some(v) = value.as_deref().filter(|v| !v.is_empty()) {
                        if let Some(n) = normalize(v, Some(base_url))? {
                            out.push(n);
                        }
                    }
                }
            }
        }
    }
    Ok(out)
}

// ---- sitemaps, fetching and the crawl loop --------------------------------------------------------------------------

pub struct Response {
    pub status: u16,
    pub content_type: String,
    pub content_len: usize,
    pub text: String,
}

/// The transport. `None` is an `httpx.HTTPError`.
pub trait Net {
    fn get(&mut self, url: &str) -> Option<Response>;
}

/// `_fetch`: the body of a successful, HTML, small-enough response.
pub fn fetch(net: &mut dyn Net, url: &str) -> Option<String> {
    let r = net.get(url)?;
    if r.status != 200
        || !r.content_type.to_lowercase().contains("html")
        || r.content_len > MAX_HTML_BYTES
    {
        return None;
    }
    Some(r.text)
}

fn loc_re() -> &'static regex::Regex {
    static R: OnceLock<regex::Regex> = OnceLock::new();
    // Python's \s also covers U+001C..U+001F
    R.get_or_init(|| {
        regex::Regex::new(r"(?s)<loc>[\s\x1c-\x1f]*(.*?)[\s\x1c-\x1f]*</loc>").unwrap()
    })
}

pub fn sitemap_urls(net: &mut dyn Net, base: &str, limit: usize) -> Result<Vec<String>, Fail> {
    let mut found: Vec<String> = Vec::new();
    let mut to_visit: VecDeque<String> = VecDeque::from([urljoin(base, "/sitemap.xml")?]);
    let mut visited: HashSet<String> = HashSet::new();
    while !to_visit.is_empty() && found.len() < limit && visited.len() < 6 {
        let sitemap = to_visit.pop_front().unwrap();
        if visited.contains(&sitemap) {
            continue;
        }
        visited.insert(sitemap.clone());
        let Some(resp) = net.get(&sitemap) else {
            continue;
        };
        if resp.status != 200 {
            continue;
        }
        for c in loc_re().captures_iter(&resp.text) {
            let loc = c[1].replace("&amp;", "&");
            if loc.to_lowercase().ends_with(".xml") {
                to_visit.push_back(loc);
            } else if let Some(n) = normalize(&loc, None)? {
                found.push(n);
            }
        }
    }
    found.truncate(limit);
    Ok(found)
}

pub fn load_robots(net: &mut dyn Net, base: &str) -> Result<Robots, Fail> {
    match net.get(&urljoin(base, "/robots.txt")?) {
        Some(r) if r.status == 200 => Ok(Robots::new(Some(&r.text))),
        _ => Ok(Robots::none()),
    }
}

#[derive(Debug, PartialEq, Eq, Clone)]
pub struct Page {
    pub url: String,
    pub title: String,
    pub text: String,
}

/// `crawl(site_url, max_pages, concurrency)`. `extract(url, html)` stands in for trafilatura.
pub fn crawl(
    site_url: &str,
    max_pages: usize,
    concurrency: usize,
    net: &mut dyn Net,
    extract: &mut dyn FnMut(&str, &str) -> Option<Page>,
) -> Result<Vec<Page>, Fail> {
    let start = normalize(site_url, None)?.ok_or(Fail::Value)?;
    let host = host_of(&start)?;
    let robots = load_robots(net, &start)?;
    let mut seeds = vec![start.clone()];
    for u in sitemap_urls(net, &start, max_pages * 3)? {
        if host_of(&u)? == host {
            seeds.push(u);
        }
    }
    let mut queue: VecDeque<String> = VecDeque::new();
    let mut seen: HashSet<String> = HashSet::new();
    for s in seeds {
        if seen.insert(s.clone()) {
            queue.push_back(s);
        }
    }
    let mut pages: Vec<Page> = Vec::new();
    while !queue.is_empty() && pages.len() < max_pages {
        let mut batch: Vec<String> = Vec::new();
        while !queue.is_empty() && batch.len() < concurrency {
            let candidate = queue.pop_front().unwrap();
            if robots.can_fetch(USER_AGENT, &candidate)? {
                batch.push(candidate);
            }
        }
        if batch.is_empty() {
            continue;
        }
        let htmls: Vec<Option<String>> = batch.iter().map(|u| fetch(net, u)).collect();
        for (url, html) in batch.iter().zip(htmls) {
            let Some(html) = html else { continue };
            if let Some(page) = extract(url, &html) {
                pages.push(page);
            }
            if seen.len() < max_pages * 10 {
                for link in extract_links(&html, url)? {
                    if host_of(&link)? == host && !seen.contains(&link) {
                        seen.insert(link.clone());
                        queue.push_back(link);
                    }
                }
            }
        }
    }
    pages.truncate(max_pages);
    Ok(pages)
}
