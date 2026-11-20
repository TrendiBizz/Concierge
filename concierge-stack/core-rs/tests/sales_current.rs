use concierge_core::sales;
use serde_json::Value;
#[test]
fn canonical_wide_sales_arithmetic() {
    let fixtures: Value =
        serde_json::from_str(include_str!("../parity/sales_current_vectors.json")).unwrap();
    for case in fixtures["forecast"].as_array().unwrap() {
        assert_eq!(
            sales::forecast(
                case["rows"].as_array().unwrap(),
                case["avg"].as_i64(),
                case["per"].as_u64().unwrap() as usize
            ),
            case["forecast"]
        );
    }
    for case in fixtures["money"].as_array().unwrap() {
        assert_eq!(
            sales::money_wide(case["cents"].as_str().unwrap().parse().unwrap()),
            case["result"].as_str().unwrap()
        );
    }
}
