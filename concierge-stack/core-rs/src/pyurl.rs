//! `urllib.parse` as CPython 3.13 implements it (`urlsplit`, `urlparse`, `urlunsplit`, `urljoin`, `urldefrag`,
//! `hostname`). Inputs Python would raise `ValueError` for are `Fail::Value`; inputs that need Unicode NFKC or an
//! IPv6 zone-id check this port does not reproduce are `Fail::Unsupported` and make no claim.
#[derive(Debug, PartialEq, Eq, Clone)]
pub enum Fail {
    /// Python raises `ValueError`.
    Value,
    /// The port declines to answer (Python would give an answer).
    Unsupported(&'static str),
}

#[derive(Debug, PartialEq, Eq, Clone, Default)]
pub struct Split {
    pub scheme: String,
    pub netloc: String,
    pub path: String,
    pub query: String,
    pub fragment: String,
}

#[derive(Debug, PartialEq, Eq, Clone)]
pub struct Parsed {
    pub split: Split,
    pub params: String,
}

const USES_RELATIVE: [&str; 20] = [
    "", "ftp", "http", "gopher", "nntp", "imap", "wais", "file", "https", "shttp", "mms",
    "prospero", "rtsp", "rtsps", "rtspu", "sftp", "svn", "svn+ssh", "ws", "wss",
];
const USES_NETLOC: [&str; 27] = [
    "",
    "ftp",
    "http",
    "gopher",
    "nntp",
    "telnet",
    "imap",
    "wais",
    "file",
    "mms",
    "https",
    "shttp",
    "snews",
    "prospero",
    "rtsp",
    "rtsps",
    "rtspu",
    "rsync",
    "svn",
    "svn+ssh",
    "sftp",
    "nfs",
    "git",
    "git+ssh",
    "ws",
    "wss",
    "itms-services",
];
const USES_PARAMS: [&str; 16] = [
    "", "ftp", "hdl", "prospero", "http", "imap", "https", "shttp", "rtsp", "rtsps", "rtspu",
    "sip", "sips", "mms", "sftp", "tel",
];

fn check_bracketed(netloc: &str) -> Result<(), Fail> {
    let hostinfo = netloc.rsplit_once('@').map_or(netloc, |(_, h)| h);
    let hostname = if let Some((before, bracketed)) = hostinfo.split_once('[') {
        if !before.is_empty() {
            return Err(Fail::Value);
        }
        let (host, port) = bracketed.split_once(']').unwrap_or((bracketed, ""));
        if !port.is_empty() && !port.starts_with(':') {
            return Err(Fail::Value);
        }
        host
    } else {
        hostinfo.split_once(':').map_or(hostinfo, |(h, _)| h)
    };
    if hostname.starts_with(['v', 'V']) {
        let ok = hostname[1..].split_once('.').is_some_and(|(hex, rest)| {
            !hex.is_empty() && hex.chars().all(|c| c.is_ascii_hexdigit()) && !rest.is_empty()
        });
        return if ok { Ok(()) } else { Err(Fail::Value) };
    }
    if hostname.contains('%') {
        return Err(Fail::Unsupported("IPv6 zone id"));
    }
    match hostname.parse::<std::net::Ipv6Addr>() {
        Ok(_) => Ok(()),
        Err(_) => Err(Fail::Value), // IPv4 in brackets and non-addresses both raise ValueError
    }
}

pub fn urlsplit(url: &str, default_scheme: &str) -> Result<Split, Fail> {
    let mut url: String = url
        .trim_start_matches(|c: char| c <= ' ')
        .chars()
        .filter(|c| !matches!(c, '\t' | '\r' | '\n'))
        .collect();
    let mut scheme = default_scheme.to_string();
    if let Some(i) = url.find(':') {
        let first = url.chars().next().unwrap_or(' ');
        if i > 0
            && first.is_ascii_alphabetic()
            && url[..i]
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c))
        {
            scheme = url[..i].to_lowercase();
            url = url[i + 1..].to_string();
        }
    }
    let mut netloc = String::new();
    if url.starts_with("//") {
        let end = url[2..].find(['/', '?', '#']).map_or(url.len(), |p| p + 2);
        netloc = url[2..end].to_string();
        url = url[end..].to_string();
        let (open, close) = (netloc.contains('['), netloc.contains(']'));
        if open != close {
            return Err(Fail::Value);
        }
        if open && close {
            check_bracketed(&netloc)?;
        }
    }
    let mut fragment = String::new();
    if let Some((a, b)) = url.split_once('#') {
        fragment = b.to_string();
        url = a.to_string();
    }
    let mut query = String::new();
    if let Some((a, b)) = url.split_once('?') {
        query = b.to_string();
        url = a.to_string();
    }
    if !netloc.is_empty() && !netloc.is_ascii() {
        return Err(Fail::Unsupported("non-ASCII netloc needs NFKC"));
    }
    Ok(Split {
        scheme,
        netloc,
        path: url,
        query,
        fragment,
    })
}

fn split_params(url: &str) -> (String, String) {
    let i = if url.contains('/') {
        match url[url.rfind('/').unwrap()..].find(';') {
            Some(p) => url.rfind('/').unwrap() + p,
            None => return (url.to_string(), String::new()),
        }
    } else {
        url.find(';').unwrap_or(0)
    };
    (url[..i].to_string(), url[i + 1..].to_string())
}

pub fn urlparse(url: &str, default_scheme: &str) -> Result<Parsed, Fail> {
    let mut split = urlsplit(url, default_scheme)?;
    let mut params = String::new();
    if USES_PARAMS.contains(&split.scheme.as_str()) && split.path.contains(';') {
        let (p, q) = split_params(&split.path);
        split.path = p;
        params = q;
    }
    Ok(Parsed { split, params })
}

pub fn urlunsplit(s: &Split) -> String {
    let mut url = s.path.clone();
    if !s.netloc.is_empty() {
        if !url.is_empty() && !url.starts_with('/') {
            url = format!("/{url}");
        }
        url = format!("//{}{}", s.netloc, url);
    } else if url.starts_with("//")
        || (!s.scheme.is_empty()
            && USES_NETLOC.contains(&s.scheme.as_str())
            && (url.is_empty() || url.starts_with('/')))
    {
        // both CPython branches prepend the same "//"
        url = format!("//{url}");
    }
    if !s.scheme.is_empty() {
        url = format!("{}:{}", s.scheme, url);
    }
    if !s.query.is_empty() {
        url = format!("{url}?{}", s.query);
    }
    if !s.fragment.is_empty() {
        url = format!("{url}#{}", s.fragment);
    }
    url
}

pub fn urlunparse(p: &Parsed) -> String {
    let mut split = p.split.clone();
    if !p.params.is_empty() {
        split.path = format!("{};{}", split.path, p.params);
    }
    urlunsplit(&split)
}

pub fn urljoin(base: &str, url: &str) -> Result<String, Fail> {
    if base.is_empty() {
        return Ok(url.to_string());
    }
    if url.is_empty() {
        return Ok(base.to_string());
    }
    let b = urlparse(base, "")?;
    let mut u = urlparse(url, &b.split.scheme)?;
    if u.split.scheme != b.split.scheme || !USES_RELATIVE.contains(&u.split.scheme.as_str()) {
        return Ok(url.to_string());
    }
    if USES_NETLOC.contains(&u.split.scheme.as_str()) {
        if !u.split.netloc.is_empty() {
            return Ok(urlunparse(&u));
        }
        u.split.netloc = b.split.netloc.clone();
    }
    if u.split.path.is_empty() && u.params.is_empty() {
        u.split.path = b.split.path.clone();
        u.params = b.params.clone();
        if u.split.query.is_empty() {
            u.split.query = b.split.query.clone();
        }
        return Ok(urlunparse(&u));
    }
    let mut base_parts: Vec<&str> = b.split.path.split('/').collect();
    if base_parts.last() != Some(&"") {
        base_parts.pop();
    }
    let mut segments: Vec<String> = if u.split.path.starts_with('/') {
        u.split.path.split('/').map(String::from).collect()
    } else {
        let mut s: Vec<String> = base_parts.iter().map(|x| x.to_string()).collect();
        s.extend(u.split.path.split('/').map(String::from));
        if s.len() >= 3 {
            let last = s.len() - 1;
            let middle: Vec<String> = s[1..last]
                .iter()
                .filter(|x| !x.is_empty())
                .cloned()
                .collect();
            let mut joined = vec![s[0].clone()];
            joined.extend(middle);
            joined.push(s[last].clone());
            s = joined;
        }
        s
    };
    let mut resolved: Vec<String> = Vec::new();
    for seg in &segments {
        match seg.as_str() {
            ".." => {
                resolved.pop();
            }
            "." => {}
            _ => resolved.push(seg.clone()),
        }
    }
    if matches!(segments.last().map(String::as_str), Some("." | "..")) {
        resolved.push(String::new());
    }
    segments.clear();
    let joined = resolved.join("/");
    u.split.path = if joined.is_empty() {
        "/".into()
    } else {
        joined
    };
    Ok(urlunparse(&u))
}

/// `urldefrag(url)[0]`.
pub fn urldefrag(url: &str) -> Result<String, Fail> {
    if url.contains('#') {
        let mut p = urlparse(url, "")?;
        p.split.fragment.clear();
        Ok(urlunparse(&p))
    } else {
        Ok(url.to_string())
    }
}

/// `urlsplit(url).hostname`.
pub fn hostname(netloc: &str) -> Option<String> {
    let hostinfo = netloc.rsplit_once('@').map_or(netloc, |(_, h)| h);
    let host = if let Some((_, bracketed)) = hostinfo.split_once('[') {
        bracketed.split_once(']').map_or(bracketed, |(h, _)| h)
    } else {
        hostinfo.split_once(':').map_or(hostinfo, |(h, _)| h)
    };
    if host.is_empty() {
        return None;
    }
    Some(match host.split_once('%') {
        Some((h, zone)) => format!("{}%{}", h.to_lowercase(), zone),
        None => host.to_lowercase(),
    })
}

/// `(username, password)` of a netloc, as `SplitResult.username` / `.password` (`None` when absent).
pub fn userinfo(netloc: &str) -> (Option<String>, Option<String>) {
    match netloc.rsplit_once('@') {
        None => (None, None),
        Some((info, _)) => match info.split_once(':') {
            Some((u, p)) => (Some(u.to_string()), Some(p.to_string())),
            None => (Some(info.to_string()), None),
        },
    }
}

/// `SplitResult.port`: `Err(Fail::Value)` is the ValueError for a non-numeric or out-of-range port.
pub fn port(netloc: &str) -> Result<Option<u32>, Fail> {
    let hostinfo = netloc.rsplit_once('@').map_or(netloc, |(_, h)| h);
    let port = if let Some((_, bracketed)) = hostinfo.split_once('[') {
        let after = bracketed.split_once(']').map_or("", |(_, a)| a);
        after.split_once(':').map_or("", |(_, p)| p)
    } else {
        hostinfo.split_once(':').map_or("", |(_, p)| p)
    };
    if port.is_empty() {
        return Ok(None);
    }
    if !port.bytes().all(|b| b.is_ascii_digit()) {
        return Err(Fail::Value);
    }
    match port.parse::<u64>() {
        Ok(n) if n <= 65535 => Ok(Some(n as u32)),
        _ => Err(Fail::Value),
    }
}
