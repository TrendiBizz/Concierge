use concierge_core::social::{self, Api, HttpErr};
use serde_json::{json, Value};

#[derive(Default)]
struct MockApi(Vec<(String, String, Option<Value>)>);
impl Api for MockApi {
    fn request(&mut self, method: &str, path: &str, data: Option<Value>) -> Result<Value, HttpErr> {
        self.0.push((method.into(), path.into(), data));
        Ok(json!({}))
    }
}
#[test]
fn youtube_operations_preserve_tenant_and_validate_before_transport() {
    let mut api = MockApi::default();
    let id = "m".repeat(32);
    for (op, args, method, suffix) in [
        ("start_youtube_oauth", vec![], "POST", "start".to_string()),
        (
            "finish_youtube_oauth",
            vec![json!(id), json!("mock-code")],
            "POST",
            "finish".to_string(),
        ),
        (
            "disconnect_youtube",
            vec![json!(id)],
            "DELETE",
            format!("accounts/{id}"),
        ),
    ] {
        social::run(&mut api, "test-business", "Test business", op, &args).unwrap();
        let call = api.0.last().unwrap();
        assert_eq!(call.0, method);
        assert_eq!(
            call.1,
            format!("/v1/customers/test-business/oauth/youtube/{suffix}")
        );
    }
    api.0.clear();
    assert!(social::run(
        &mut api,
        "test-business",
        "Test business",
        "finish_youtube_oauth",
        &[json!("bad"), json!("mock-code")]
    )
    .is_err());
    assert!(social::run(
        &mut api,
        "test-business",
        "Test business",
        "disconnect_youtube",
        &[json!("../other")]
    )
    .is_err());
    assert!(api.0.is_empty());
}
#[test]
fn youtube_error_mapping_only_returns_static_messages() {
    let path = "/v1/customers/test-business/oauth/youtube/finish";
    let allowed = "YouTube did not grant upload access";
    assert_eq!(
        social::response(400, path, Ok(json!({"error":allowed}))),
        Err(social::Failure::Http(HttpErr {
            status: 400,
            detail: allowed.into()
        }))
    );
    assert_eq!(
        social::response(400, path, Ok(json!({"error":"untrusted provider detail"}))),
        Err(social::Failure::Http(HttpErr {
            status: 400,
            detail: "Social request could not be completed".into()
        }))
    );
}
