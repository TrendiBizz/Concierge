use crate::{is_py_space, py_strip};

/// Split on sentence boundaries (whitespace run preceded by `.`, `!` or `?`), as
/// Python's `re.split(r"(?<=[.!?])\s+", ...)`.
fn split_sentences(text: &str) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let mut out = Vec::new();
    let mut current = String::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        let prev_is_end = i > 0 && matches!(chars[i - 1], '.' | '!' | '?');
        if is_py_space(c) && prev_is_end {
            while i < chars.len() && is_py_space(chars[i]) {
                i += 1;
            }
            out.push(std::mem::take(&mut current));
        } else {
            current.push(c);
            i += 1;
        }
    }
    out.push(current);
    out
}

/// Split paragraphs on `\n\s*\n`, as Python's `re.split(r"\n\s*\n", ...)`.
fn split_paragraphs(text: &str) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let mut out = Vec::new();
    let mut current = String::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '\n' {
            // Greedy `\s*` then a final `\n`: take the longest whitespace run, back off to its last newline.
            let mut j = i + 1;
            while j < chars.len() && is_py_space(chars[j]) {
                j += 1;
            }
            if let Some(last_nl) = (i + 1..j).rev().find(|&k| chars[k] == '\n') {
                out.push(std::mem::take(&mut current));
                i = last_nl + 1;
                continue;
            }
        }
        current.push(chars[i]);
        i += 1;
    }
    out.push(current);
    out
}

fn char_len(s: &str) -> usize {
    s.chars().count()
}

fn tail_chars(s: &str, n: usize) -> String {
    let len = char_len(s);
    s.chars().skip(len.saturating_sub(n)).collect()
}

fn split_long(paragraph: &str, max_chars: usize) -> Vec<String> {
    let mut pieces = Vec::new();
    let mut current = String::new();
    for sentence in split_sentences(paragraph) {
        if char_len(&sentence) > max_chars {
            if !current.is_empty() {
                pieces.push(std::mem::take(&mut current));
            }
            let chars: Vec<char> = sentence.chars().collect();
            for piece in chars.chunks(max_chars.max(1)) {
                pieces.push(piece.iter().collect());
            }
            continue;
        }
        if !current.is_empty() && char_len(&current) + 1 + char_len(&sentence) > max_chars {
            pieces.push(std::mem::replace(&mut current, sentence));
        } else {
            current = py_strip(&format!("{current} {sentence}")).to_string();
        }
    }
    if !current.is_empty() {
        pieces.push(current);
    }
    pieces
}

/// Split text into chunks of at most ~`max_chars`, preferring paragraph boundaries, with up to
/// `overlap` characters of trailing context shared between consecutive chunks.
pub fn chunk_text(text: &str, max_chars: usize, overlap: usize) -> Vec<String> {
    let text = py_strip(text);
    if text.is_empty() {
        return Vec::new();
    }
    let mut units: Vec<String> = Vec::new();
    for p in split_paragraphs(text) {
        let p = py_strip(&p);
        if p.is_empty() {
            continue;
        }
        if char_len(p) > max_chars {
            units.extend(split_long(p, max_chars));
        } else {
            units.push(p.to_string());
        }
    }

    let mut chunks = Vec::new();
    let mut current = String::new();
    for unit in units {
        if !current.is_empty() && char_len(&current) + 2 + char_len(&unit) > max_chars {
            chunks.push(current.clone());
            let mut tail = if overlap > 0 {
                tail_chars(&current, overlap)
            } else {
                String::new()
            };
            if let Some((_, rest)) = tail.split_once(' ') {
                tail = rest.to_string();
            }
            current = if tail.is_empty() {
                unit
            } else {
                py_strip(&format!("{tail}\n\n{unit}")).to_string()
            };
        } else if current.is_empty() {
            current = unit;
        } else {
            current = format!("{current}\n\n{unit}");
        }
    }
    if !current.is_empty() {
        chunks.push(current);
    }
    chunks
}
