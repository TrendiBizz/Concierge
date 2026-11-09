//! `json.dumps(value)` with Python's defaults (`ensure_ascii=True`, `", "` and `": "` separators), for the shapes the API
//! stores in JSONB parameters. Floats have a different shortest-repr in Python, so they return `None` rather than guess.
use serde_json::Value;

fn push_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                // ensure_ascii escapes DEL's neighbours the same way only above 0x7f; 0x7f itself is printed as is.
                if c as u32 == 0x7f {
                    out.push(c);
                } else {
                    let mut buf = [0u16; 2];
                    for unit in c.encode_utf16(&mut buf) {
                        out.push_str(&format!("\\u{:04x}", unit));
                    }
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

pub fn dumps(v: &Value) -> Option<String> {
    let mut out = String::new();
    write(&mut out, v)?;
    Some(out)
}

fn write(out: &mut String, v: &Value) -> Option<()> {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) if n.is_i64() || n.is_u64() => out.push_str(&n.to_string()),
        Value::Number(_) => return None,
        Value::String(s) => push_string(out, s),
        Value::Array(a) => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                write(out, x)?;
            }
            out.push(']');
        }
        Value::Object(m) => {
            out.push('{');
            for (i, (k, x)) in m.iter().enumerate() {
                if i > 0 {
                    out.push_str(", ");
                }
                push_string(out, k);
                out.push_str(": ");
                write(out, x)?;
            }
            out.push('}');
        }
    }
    Some(())
}
