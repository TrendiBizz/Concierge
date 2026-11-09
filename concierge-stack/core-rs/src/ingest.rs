//! Port of the pure rules in `ingest.py` and `embeddings.to_pgvector`: how pages become embeddable records, the exact
//! database operations a replacement performs (embedding happens first so a failure never wipes saved knowledge), and
//! the demo-question prompt and parser. Crawling, embedding and SQL execution stay outside.
use crate::chunking::chunk_text;
use crate::pyjson;
use crate::{py_splitlines, py_strip};
use serde_json::{json, Value};

pub const MANUAL_PREFIX: &str = "manual:";

pub const SQL_LOCK: &str = "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))";
pub const SQL_DELETE_URL: &str = "DELETE FROM chunks WHERE tenant_id=$1 AND url=$2";
pub const SQL_DELETE_CRAWLED: &str = "DELETE FROM chunks WHERE tenant_id = $1 AND url NOT LIKE $2";
pub const SQL_INSERT: &str = "INSERT INTO chunks (tenant_id, url, title, content, embedding) VALUES ($1, $2, $3, $4, $5::text::vector)";

pub struct Page<'a> {
    pub url: &'a str,
    pub title: &'a str,
    pub text: &'a str,
}

#[derive(Debug, PartialEq, Eq, Clone)]
pub struct Record {
    pub url: String,
    pub title: String,
    pub text: String,
}

/// Every chunk of every page, prefixed with the page title so short chunks keep their context.
pub fn records(pages: &[Page]) -> Vec<Record> {
    let mut out = Vec::new();
    for page in pages {
        for chunk in chunk_text(page.text, 1000, 150) {
            let text = if page.title.is_empty() {
                chunk
            } else {
                format!("{}\n\n{}", page.title, chunk)
            };
            out.push(Record {
                url: page.url.into(),
                title: page.title.into(),
                text,
            });
        }
    }
    out
}

/// `to_pgvector`: `[x.xxxxxx,...]` with Python's spelling of non-finite values.
pub fn to_pgvector(vec: &[f64]) -> String {
    let parts: Vec<String> = vec
        .iter()
        .map(|x| {
            if x.is_nan() {
                "nan".to_string()
            } else if x.is_infinite() {
                if *x > 0.0 { "inf" } else { "-inf" }.to_string()
            } else {
                format!("{x:.6}")
            }
        })
        .collect();
    format!("[{}]", parts.join(","))
}

#[derive(Debug, PartialEq)]
pub enum Op {
    Execute {
        sql: &'static str,
        args: Vec<Value>,
    },
    ExecuteMany {
        sql: &'static str,
        rows: Vec<Vec<Value>>,
    },
}

/// The transaction `_store` runs once embeddings exist. `Err` is the `RuntimeError` for a short embedding list.
pub fn store_plan(
    tenant_id: &str,
    records: &[Record],
    vectors: &[Vec<f64>],
    replace_crawled: bool,
    replace_url: Option<&str>,
) -> Result<Vec<Op>, &'static str> {
    if vectors.len() != records.len() {
        return Err("Incomplete document embeddings");
    }
    let mut ops = Vec::new();
    if let Some(url) = replace_url {
        ops.push(Op::Execute {
            sql: SQL_LOCK,
            args: vec![json!(format!("knowledge:{tenant_id}:{url}"))],
        });
        ops.push(Op::Execute {
            sql: SQL_DELETE_URL,
            args: vec![json!(tenant_id), json!(url)],
        });
    }
    if replace_crawled {
        ops.push(Op::Execute {
            sql: SQL_DELETE_CRAWLED,
            args: vec![json!(tenant_id), json!(format!("{MANUAL_PREFIX}%"))],
        });
    }
    ops.push(Op::ExecuteMany {
        sql: SQL_INSERT,
        rows: records
            .iter()
            .zip(vectors)
            .map(|(r, v)| {
                vec![
                    json!(tenant_id),
                    json!(r.url),
                    json!(r.title),
                    json!(r.text),
                    json!(to_pgvector(v)),
                ]
            })
            .collect(),
    });
    Ok(ops)
}

pub struct DemoRow<'a> {
    pub title: &'a str,
    pub content: &'a str,
}

/// The chat messages sent to the model for `generate_demo_questions`.
pub fn demo_messages(name: &str, rows: &[DemoRow], count: usize) -> Value {
    let sample: String = rows
        .iter()
        .map(|r| format!("{}\n{}", r.title, r.content))
        .collect::<Vec<_>>()
        .join("\n\n")
        .chars()
        .take(7000)
        .collect();
    json!([
        {"role": "system", "content": format!(
            "You prepare live demos of a website AI assistant. Given a business's website content, write {count} realistic, specific questions a customer might ask that this content can answer and that would impress the owner (niche specialties, pricing, compatibility, edge cases). One question per line, no numbering, no extra text.")},
        {"role": "user", "content": format!("Business: {name}\n\n{sample}")},
    ])
}

/// One question per non-blank line, list markers and digits trimmed from both ends, at most `count`.
pub fn parse_questions(content: Option<&str>, count: usize) -> Vec<String> {
    const TRIM: &str = " -\u{2022}\t0123456789.";
    py_splitlines(content.unwrap_or(""))
        .into_iter()
        .filter(|l| !py_strip(l).is_empty())
        .map(|l| py_strip(l.trim_matches(|c| TRIM.contains(c))).to_string())
        .take(count)
        .collect()
}

/// The `$2::jsonb` parameter that stores the questions.
pub fn questions_json(questions: &[String]) -> Option<String> {
    pyjson::dumps(&Value::Array(questions.iter().map(|q| json!(q)).collect()))
}
