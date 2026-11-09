//! Port of the sandbox demo page in `main.py` (`GET /demo/{slug}`).
//!
//! The page is a pure function of the tenant row, the first knowledge chunk and the `presenter` query value, so the
//! HTML can be compared byte for byte with the live Python without a database. The two SQL statements (the tenant by
//! slug and the first chunk by id) live in `concierge-server`, which is the only crate allowed to talk to PostgreSQL.
//!
//! Where Python would raise (and FastAPI answer a plain 500) this returns `Err`, and the server answers the same 500:
//! a missing or non-text `name` / `accent_color` / `public_key`, a `demo_questions` value Python cannot iterate, a list
//! entry that is not text, or a string that is not JSON. One shape is declined rather than reproduced: a non-empty JSON
//! *object* in `demo_questions` (Python iterates its keys in PostgreSQL's `jsonb` order, which differs from `serde_json`'s
//! key order). It also fails closed with `Err`, and is listed in `PORT_STATUS.md`.
use crate::pyval;
use crate::report::html_escape;
use serde_json::Value;

/// Characters of the first chunk shown on the page: Python's `excerpt[:700]` counts code points, not bytes.
pub const EXCERPT_CHARS: usize = 700;

/// `demo_questions` as `demo_page` sees it. `tenants._load` has already decoded the column once; if the result is
/// still text, `demo_page` decodes it a second time (`json.loads`), and a failure there is a 500.
fn questions_value(tenant: &Value) -> Result<Value, &'static str> {
    match tenant.get("demo_questions") {
        None => Err("demo_questions missing"),
        Some(Value::String(text)) => {
            serde_json::from_str(text).map_err(|_| "demo_questions is not JSON")
        }
        Some(other) => Ok(other.clone()),
    }
}

/// Python's `for q in questions` followed by `html.escape(q)`: a list of text, or the characters of a text.
fn question_items(questions: &Value) -> Result<Vec<String>, &'static str> {
    match questions {
        Value::Array(items) => items
            .iter()
            .map(|q| q.as_str().map(html_escape).ok_or("question is not text"))
            .collect(),
        Value::String(text) => Ok(text.chars().map(|c| html_escape(&c.to_string())).collect()),
        Value::Object(_) => Err("object demo_questions declined"),
        _ => Err("demo_questions is not iterable"),
    }
}

fn text<'a>(tenant: &'a Value, key: &str) -> Result<&'a str, &'static str> {
    tenant
        .get(key)
        .and_then(Value::as_str)
        .ok_or("tenant field is not text")
}

/// `demo_page`: `excerpt` is the `content` of the tenant's first chunk by id (`None` when it has none), `presenter`
/// the parsed `?presenter=` integer (0 when absent).
pub fn demo_page(
    tenant: &Value,
    excerpt: Option<&str>,
    presenter: i128,
) -> Result<String, &'static str> {
    let name = html_escape(text(tenant, "name")?);
    let excerpt_html = html_escape(
        &excerpt
            .unwrap_or("")
            .chars()
            .take(EXCERPT_CHARS)
            .collect::<String>(),
    )
    .replace('\n', "<br>");
    let site = match tenant.get("site_url") {
        Some(Value::String(s)) => s.as_str(),
        _ => "",
    };
    let site_html = if site.starts_with("http://") || site.starts_with("https://") {
        html_escape(site)
    } else {
        String::new()
    };

    // Decoded even when `presenter` is 0, exactly as Python does it before looking at `presenter`.
    let questions = questions_value(tenant)?;
    let panel = if presenter != 0 && pyval::truthy(Some(&questions)) {
        let items: String = question_items(&questions)?
            .iter()
            .map(|q| format!("<li>{q}</li>"))
            .collect();
        format!("<aside><h2>Questions to ask</h2><ol>{items}</ol></aside>")
    } else {
        String::new()
    };

    let accent = html_escape(text(tenant, "accent_color")?);
    let key = html_escape(text(tenant, "public_key")?);
    let subtitle = if site_html.is_empty() {
        String::new()
    } else {
        format!(" - {site_html}")
    };
    Ok(format!(
        r#"<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} - AI guide demo</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;color:#111;background:#fafafa}}
 header{{padding:24px;background:{accent};color:#fff}}
 main{{max-width:760px;margin:32px auto;padding:0 16px;line-height:1.6}}
 aside{{position:fixed;left:16px;bottom:16px;max-width:380px;background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px 16px;font-size:14px}}
 small{{color:#666}}
</style></head>
<body>
<header><h1 style="margin:0">{name}</h1><small style="color:#fff;opacity:.85">Sandbox preview of your AI guide{subtitle}</small></header>
<main><p>{excerpt_html}</p></main>
{panel}
<script src="/widget.js" data-key="{key}" data-autoopen="1" defer></script>
</body></html>"#
    ))
}
