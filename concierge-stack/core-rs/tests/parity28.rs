//! Batch 28: Starlette's `FileResponse` (stat headers, `Range`, `If-Range`, multipart). The vectors are produced by the
//! live Starlette, with real files for the stat headers (`parity/gen_vectors28.py` -> `parity/vectors28.json`).
use concierge_core::static_file::{self as sf, RangeError, Stat};
use serde_json::Value;

fn vectors() -> Value {
    serde_json::from_str(include_str!("../parity/vectors28.json")).unwrap()
}

#[test]
fn stat_headers_match_starlette() {
    let v = vectors();
    let cases = v["stat"].as_array().unwrap();
    assert!(cases.len() >= 10);
    for c in cases {
        let ns = c["mtime_ns"].as_i64().unwrap();
        let stat = Stat {
            size: c["size"].as_u64().unwrap(),
            mtime_secs: ns.div_euclid(1_000_000_000),
            mtime_nanos: ns.rem_euclid(1_000_000_000) as u32,
        };
        assert_eq!(
            stat.mtime_repr(),
            c["mtime_repr"].as_str().unwrap(),
            "mtime {ns}"
        );
        assert_eq!(stat.etag(), c["etag"].as_str().unwrap(), "etag {ns}");
        assert_eq!(
            stat.last_modified(),
            c["last_modified"].as_str().unwrap(),
            "last-modified {ns}"
        );
    }
}

#[test]
fn range_parsing_matches_starlette() {
    let v = vectors();
    let (mut compared, mut declined) = (0, 0);
    for c in v["range"].as_array().unwrap() {
        let header = c["header"].as_str().unwrap();
        let size = i128::from(c["size"].as_i64().unwrap());
        let got = sf::parse_range_header(header, size);
        let want = if let Some(ok) = c.get("ok") {
            Ok(ok
                .as_array()
                .unwrap()
                .iter()
                .map(|p| {
                    (
                        i128::from(p[0].as_i64().unwrap()),
                        i128::from(p[1].as_i64().unwrap()),
                    )
                })
                .collect::<Vec<_>>())
        } else if let Some(m) = c.get("malformed") {
            Err(RangeError::Malformed(m.as_str().unwrap().to_string()))
        } else {
            Err(RangeError::NotSatisfiable(i128::from(
                c["unsat"].as_i64().unwrap(),
            )))
        };
        if c.get("declined").is_some() {
            // Python parses Unicode digits; this port either gives Python's answer or refuses, never a different one.
            assert!(
                got == want || got == Err(RangeError::Unsupported),
                "Range {header:?} on a {size}-byte file: {got:?} vs {want:?}"
            );
            declined += 1;
            continue;
        }
        assert_eq!(got, want, "Range {header:?} on a {size}-byte file");
        compared += 1;
    }
    assert!(compared > 400, "only {compared} compared");
    assert!(declined > 0);
}

#[test]
fn if_range_matches_starlette() {
    let v = vectors();
    for c in v["if_range"].as_array().unwrap() {
        let got = sf::should_use_range(
            c["value"].as_str().unwrap(),
            c["last_modified"].as_str().unwrap(),
            c["etag"].as_str().unwrap(),
        );
        assert_eq!(got, c["use"].as_bool().unwrap(), "If-Range {}", c["value"]);
    }
}

#[test]
fn multipart_matches_starlette() {
    let v = vectors();
    for c in v["multipart"].as_array().unwrap() {
        let ranges: Vec<(i128, i128)> = c["ranges"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| {
                (
                    i128::from(p[0].as_i64().unwrap()),
                    i128::from(p[1].as_i64().unwrap()),
                )
            })
            .collect();
        let size = i128::from(c["size"].as_i64().unwrap());
        let (boundary, ctype) = (
            c["boundary"].as_str().unwrap(),
            c["content_type"].as_str().unwrap(),
        );
        assert_eq!(
            sf::multipart_content_length(&ranges, boundary, size, ctype),
            i128::from(c["length"].as_i64().unwrap())
        );
        let headers = c["headers"].as_array().unwrap();
        for (i, &(s, e)) in ranges.iter().enumerate() {
            assert_eq!(
                sf::multipart_part_header(boundary, ctype, s, e, size),
                headers[i].as_str().unwrap()
            );
        }
    }
}
