//! Friendly owner errors retain schema ordering and never echo submitted values.
use axum::http::HeaderMap;
use concierge_core::requests::{self, Outcome, Ty};
use serde_json::Value;

pub(crate) fn parse(bytes: &[u8], headers: &HeaderMap, model: &str) -> Result<Value, String> {
    if headers.get("content-type").is_some_and(|h| {
        let media = h
            .to_str()
            .unwrap_or("")
            .split(';')
            .next()
            .unwrap_or("")
            .trim()
            .to_lowercase();
        media != "application/json"
            && !(media.starts_with("application/") && media.ends_with("+json"))
    }) {
        return Err("Value is not valid.".into());
    }
    if bytes.is_empty() {
        return Err("Value is required.".into());
    }
    let value: Value = serde_json::from_slice(bytes).map_err(|e| {
        // serde's column is one-based; FastAPI reports the zero-based JSON offset.
        let preceding: usize = bytes
            .split(|b| *b == b'\n')
            .take(e.line().saturating_sub(1))
            .map(|l| l.len() + 1)
            .sum();
        format!("{} is not valid.", preceding + e.column().saturating_sub(1))
    })?;
    validate(&value, model)
}

pub(crate) fn validate(value: &Value, model: &str) -> Result<Value, String> {
    match requests::validate(model, value) {
        Ok(v) => Ok(v),
        Err(Outcome::Unsupported(_)) => Err("Value is not valid.".into()),
        Err(Outcome::Errors(errors)) => {
            let (fields, _) = requests::model(model).unwrap();
            let mut messages = Vec::new();
            for e in errors.iter().take(3) {
                let field = e
                    .loc
                    .rsplit('.')
                    .find(|s| !s.is_empty() && !["body", "query", "path"].contains(s))
                    .unwrap_or("value");
                let label = match field {
                    "token" => "Invitation link".into(),
                    "email" => "Email address".into(),
                    "slug" => "Business ID".into(),
                    _ => {
                        let v = field.replace('_', " ");
                        let mut chars = v.chars();
                        chars
                            .next()
                            .map(|c| c.to_uppercase().collect::<String>() + chars.as_str())
                            .unwrap_or_else(|| "Value".into())
                    }
                };
                let message = if field == "token"
                    && ["string_too_short", "string_too_long", "missing"].contains(&e.ty)
                {
                    "The invitation link looks incomplete. Open it again from your email.".into()
                } else {
                    match e.ty {
                        "missing" => format!("{label} is required."),
                        "string_too_short" | "string_too_long" => {
                            match fields
                                .iter()
                                .find(|f| f.name == e.loc.rsplit('.').next().unwrap_or(field))
                                .map(|f| &f.ty)
                            {
                                Some(Ty::Str { min, .. }) if e.ty == "string_too_short" => {
                                    format!("{label} must be at least {min} characters.")
                                }
                                Some(Ty::Str { max: Some(max), .. }) => {
                                    format!("{label} must be at most {max} characters.")
                                }
                                _ => format!("{label} is not valid."),
                            }
                        }
                        _ => format!("{label} is not valid."),
                    }
                };
                if !messages.contains(&message) {
                    messages.push(message)
                }
            }
            Err(messages.join(" "))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn canonical_friendly_validation_errors() {
        let cases: Vec<Value> = serde_json::from_str(include_str!(
            "../../core-rs/parity/owner_model_vectors.json"
        ))
        .unwrap();
        for case in cases {
            if let Some(expected) = case.get("friendly") {
                let got = validate(&case["body"], case["model"].as_str().unwrap()).unwrap_err();
                assert_eq!(
                    got,
                    expected.as_str().unwrap(),
                    "model={} body={}",
                    case["model"],
                    case["body"]
                );
            }
        }
    }
}
