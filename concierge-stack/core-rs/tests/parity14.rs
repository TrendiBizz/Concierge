//! Batch 14: the crawler (URL handling, link extraction, robots.txt, sitemaps, fetch rules, crawl loop) against vectors
//! produced by the live Python (`app.crawler`, urllib.parse, html.parser, urllib.robotparser) with a fake network.
use concierge_core::crawler::{self, Net, Page, Response};
use concierge_core::pyurl::{urldefrag, urljoin, Fail};
use concierge_core::robots::{normalize, normalize_uri, Robots};
use serde_json::{json, Value};

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors14.json")).unwrap()
}

/// Compare a Rust result with the recorded Python outcome. `Unsupported` is a declined answer: it is allowed only where
/// Python gave an answer, and the caller counts it so a regression to "declines everything" fails.
fn check<T: PartialEq + std::fmt::Debug>(
    got: Result<T, Fail>,
    want: &Value,
    conv: impl Fn(&Value) -> T,
    declined: &mut usize,
    what: &str,
) {
    match got {
        Ok(v) => {
            // a Python exception must never be matched by a returned value (a null "ok" is a real `None`)
            assert!(
                want.get("ok").is_some(),
                "{what}: Python raised but Rust answered: {want}"
            );
            assert_eq!(v, conv(&want["ok"]), "{what} {want}");
        }
        Err(Fail::Value) => assert_eq!(want["err"], "ValueError", "{what} {want}"),
        Err(Fail::Unsupported(reason)) => {
            // only the two documented reasons may decline, never anything else
            assert!(
                matches!(reason, "non-ASCII netloc needs NFKC" | "IPv6 zone id"),
                "{what}: undocumented decline {reason}"
            );
            *declined += 1;
        }
    }
}

#[test]
fn url_handling_matches_python() {
    let v = vectors();
    let (mut declined, mut total) = (0, 0);
    for c in v["urls"]["norm"].as_array().unwrap() {
        total += 1;
        let got = crawler::normalize(c["url"].as_str().unwrap(), c["base"].as_str());
        check(
            got,
            &c["out"],
            |x| x.as_str().map(String::from),
            &mut declined,
            "normalize",
        );
    }
    for c in v["urls"]["join"].as_array().unwrap() {
        total += 1;
        let got = urljoin(c["base"].as_str().unwrap(), c["url"].as_str().unwrap());
        check(
            got,
            &c["out"],
            |x| x.as_str().unwrap().to_string(),
            &mut declined,
            "urljoin",
        );
    }
    for c in v["urls"]["defrag"].as_array().unwrap() {
        total += 1;
        let got = urldefrag(c["url"].as_str().unwrap());
        check(
            got,
            &c["out"],
            |x| x.as_str().unwrap().to_string(),
            &mut declined,
            "urldefrag",
        );
    }
    for c in v["urls"]["host"].as_array().unwrap() {
        total += 1;
        let got = crawler::host_of(c["url"].as_str().unwrap());
        check(
            got,
            &c["out"],
            |x| x.as_str().unwrap().to_string(),
            &mut declined,
            "host_of",
        );
    }
    assert!(total > 12_000, "{total}");
    // the corpus deliberately over-samples internationalised hosts (about 1 in 20 URLs)
    assert!(declined * 25 < total, "declined {declined} of {total}");
}

fn tag_json(tags: &[crawler::Tag]) -> Value {
    Value::Array(
        tags.iter()
            .map(|t| {
                json!([
                    t.name,
                    t.attrs
                        .iter()
                        .map(|(k, v)| json!([k, v]))
                        .collect::<Vec<_>>()
                ])
            })
            .collect(),
    )
}

#[test]
fn html_start_tags_match_python() {
    let v = vectors();
    let mut with_tags = 0;
    for c in v["html"]["tags"].as_array().unwrap() {
        let html = c["html"].as_str().unwrap();
        let got = crawler::start_tags(html).unwrap_or_else(|e| panic!("{e:?} for {html:?}"));
        let got = json!({"ok": tag_json(&got)});
        assert_eq!(got, c["out"], "{html:?}");
        if !c["out"]["ok"].as_array().unwrap().is_empty() {
            with_tags += 1;
        }
    }
    assert!(with_tags > 1500, "{with_tags}");
}

#[test]
fn link_extraction_matches_python() {
    let v = vectors();
    let mut nonempty = 0;
    for c in v["html"]["links"].as_array().unwrap() {
        let html = c["html"].as_str().unwrap();
        let mut declined = 0;
        let got = crawler::extract_links(html, c["base"].as_str().unwrap());
        check(
            got,
            &c["out"],
            |x| {
                x.as_array()
                    .unwrap()
                    .iter()
                    .map(|s| s.as_str().unwrap().to_string())
                    .collect::<Vec<_>>()
            },
            &mut declined,
            "links",
        );
        assert_eq!(declined, 0, "{html:?}");
        if c["out"]["ok"].as_array().is_some_and(|a| !a.is_empty()) {
            nonempty += 1;
        }
    }
    assert!(nonempty > 1000, "{nonempty}");
}

#[test]
fn robots_decisions_match_python() {
    let v = vectors();
    let (mut denied, mut allowed) = (0, 0);
    for r in v["robots"].as_array().unwrap() {
        let text = r["text"].as_str().unwrap();
        let robots = Robots::new(Some(text));
        for c in r["checks"].as_array().unwrap() {
            let got = robots
                .can_fetch(c["ua"].as_str().unwrap(), c["url"].as_str().unwrap())
                .unwrap();
            assert_eq!(got, c["allowed"].as_bool().unwrap(), "{text:?} {c}");
            if got {
                allowed += 1;
            } else {
                denied += 1;
            }
        }
    }
    assert!(denied > 400 && allowed > 400, "{denied} {allowed}");
    for q in v["quote"].as_array().unwrap() {
        let s = q["in"].as_str().unwrap();
        assert_eq!(normalize(s), q["norm"].as_str().unwrap(), "{s:?}");
        assert_eq!(normalize_uri(s), q["uri"].as_str().unwrap(), "{s:?}");
    }
}

/// A network that serves a recorded site and logs every request, like the Python fake.
struct SpecNet<'a> {
    spec: &'a Value,
    log: Vec<String>,
}

impl Net for SpecNet<'_> {
    fn get(&mut self, url: &str) -> Option<Response> {
        self.log.push(url.to_string());
        let r = self.spec.get(url)?;
        if r == "fail" {
            return None;
        }
        let text = r["text"].as_str().unwrap_or("").to_string();
        Some(Response {
            status: r["status"].as_u64().unwrap_or(200) as u16,
            content_type: r["ctype"].as_str().unwrap_or("text/html").to_string(),
            content_len: r["size"].as_u64().map(|n| n as usize).unwrap_or(text.len()),
            text,
        })
    }
}

fn strs(v: &Value) -> Vec<String> {
    v.as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap().to_string())
        .collect()
}

#[test]
fn sitemaps_match_python() {
    for c in vectors()["sitemap"].as_array().unwrap() {
        let mut net = SpecNet {
            spec: &c["spec"],
            log: vec![],
        };
        let got = crawler::sitemap_urls(
            &mut net,
            "https://example.com/",
            c["limit"].as_u64().unwrap() as usize,
        );
        match got {
            Ok(urls) => assert_eq!(urls, strs(&c["out"]["ok"]), "{c}"),
            Err(Fail::Value) => assert_eq!(c["out"]["err"], "ValueError"),
            Err(e) => panic!("{e:?} {c}"),
        }
        assert_eq!(net.log, strs(&c["log"]), "{c}");
    }
}

#[test]
fn fetch_rules_match_python() {
    for c in vectors()["fetch"].as_array().unwrap() {
        let spec = if c["status"] == "fail" {
            json!({})
        } else {
            json!({"https://e.com/p": {"status": c["status"], "ctype": c["ctype"], "text": "BODY", "size": c["size"]}})
        };
        let mut net = SpecNet {
            spec: &spec,
            log: vec![],
        };
        let got = crawler::fetch(&mut net, "https://e.com/p");
        assert_eq!(got.as_deref(), c["out"].as_str(), "{c}");
    }
}

#[test]
fn crawl_loop_matches_python() {
    let mut with_pages = 0;
    for c in vectors()["crawl"].as_array().unwrap() {
        let mut net = SpecNet {
            spec: &c["spec"],
            log: vec![],
        };
        let mut extract = |url: &str, html: &str| -> Option<Page> {
            if html.contains("noextract") {
                return None;
            }
            Some(Page {
                url: url.into(),
                title: format!("T{}", html.chars().count() % 7),
                text: html.chars().take(30).collect(),
            })
        };
        let got = crawler::crawl(
            c["start"].as_str().unwrap(),
            c["max_pages"].as_u64().unwrap() as usize,
            c["concurrency"].as_u64().unwrap() as usize,
            &mut net,
            &mut extract,
        );
        match got {
            Ok(pages) => {
                let want: Vec<Vec<String>> = c["out"]["ok"]
                    .as_array()
                    .unwrap_or_else(|| panic!("Python raised but Rust returned pages: {c}"))
                    .iter()
                    .map(strs)
                    .collect();
                let have: Vec<Vec<String>> = pages
                    .iter()
                    .map(|p| vec![p.url.clone(), p.title.clone(), p.text.clone()])
                    .collect();
                assert_eq!(have, want, "{}", c["start"]);
                if !have.is_empty() {
                    with_pages += 1;
                }
            }
            Err(Fail::Value) => assert_eq!(c["out"]["err"], "ValueError", "{c}"),
            Err(e) => panic!("{e:?} {c}"),
        }
        assert_eq!(
            net.log,
            strs(&c["log"]),
            "request sequence differs: {}",
            c["start"]
        );
    }
    assert!(with_pages > 60, "{with_pages}");
}
