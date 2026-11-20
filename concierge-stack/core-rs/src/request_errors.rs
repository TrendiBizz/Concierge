//! Structured Pydantic-compatible errors for internal action contracts.
use crate::{
    pydantic::FieldErr,
    requests::{self, Ty},
};
use serde_json::{json, Value};
fn literal(values: &[&str]) -> String {
    let parts: Vec<_> = values.iter().map(|s| format!("'{s}'")).collect();
    match parts.len() {
        0 => String::new(),
        1 => parts[0].clone(),
        2 => parts.join(" or "),
        n => format!("{} or {}", parts[..n - 1].join(", "), parts[n - 1]),
    }
}
pub fn format_errors(model: &str, body: &Value, errors: &[FieldErr], prefix: bool) -> Value {
    Value::Array(errors.iter().map(|e|{
  let mut schema=model.to_string();let mut current=body;let mut parent=body;let mut ty=None;let mut loc=Vec::new();
  if prefix{loc.push(json!("body"));}
  for part in e.loc.split('.').filter(|p|!p.is_empty()) {
   parent=current;
   if let Ok(i)=part.parse::<usize>(){loc.push(json!(i));current=current.get(i).unwrap_or(&Value::Null);continue}
   loc.push(json!(part));
   ty=requests::model(&schema).and_then(|(fields,_)|fields.into_iter().find(|f|f.name==part)).map(|f|f.ty);
   match &ty{Some(Ty::Model(m))|Some(Ty::ListModel{model:m,..})=>schema=m.to_string(),_=>()}
   current=current.get(part).unwrap_or(&Value::Null);
  }
  let mut kind=e.ty;let mut ctx=None;
  let message=match e.ty {
   "missing"=>"Field required".to_string(),
   "extra_forbidden"=>"Extra inputs are not permitted".into(),
   "string_type"=>"Input should be a valid string".into(),
   "bool_type"=>"Input should be a valid boolean".into(),
   "bool_parsing"=>"Input should be a valid boolean, unable to interpret input".into(),
   "int_type"=>"Input should be a valid integer".into(),
   "int_parsing"=>"Input should be a valid integer, unable to parse string as an integer".into(),
   "int_from_float"=>"Input should be a valid integer, got a number with a fractional part".into(),
   "dict_type"=>"Input should be a valid dictionary".into(),
   "list_type"=>"Input should be a valid list".into(),
   "model_type"=>{if prefix{kind="model_attributes_type";"Input should be a valid dictionary or object to extract fields from".into()}else{ctx=Some(json!({"class_name":match schema.as_str(){"CaseBundle"=>"Bundle","CaseAction"=>"Action","CaseDelivery"=>"Delivery","ActionAutomation"=>"AutomationBody",m=>m}}));format!("Input should be a valid dictionary or instance of {}",ctx.as_ref().unwrap()["class_name"].as_str().unwrap())}},
   "uuid_type"=>"UUID input should be a string, bytes or UUID object".into(),
   "uuid_parsing"=>{let text=current.as_str().unwrap_or("");let reason=if !text.is_ascii() && text.len()<=45 {if let Some((index,c))=text.char_indices().find(|(_,c)|!(*c as u8).is_ascii_hexdigit() && *c!='-'){format!("invalid character: found `{c}` at {index}")}else{format!("invalid length: found {}",text.len())}}else{uuid::Uuid::parse_str(text).unwrap_err().to_string()};ctx=Some(json!({"error":reason}));format!("Input should be a valid UUID, {reason}")},
   "literal_error"=>{let allowed=match &ty{Some(Ty::Lit(v))=>literal(v),_=>String::new()};ctx=Some(json!({"expected":allowed}));format!("Input should be {allowed}")},
   "string_too_short"=>{let min=match ty{Some(Ty::Str{min,..})=>min,_=>0};ctx=Some(json!({"min_length":min}));format!("String should have at least {min} character{}",if min==1{""}else{"s"})},
   "string_too_long"=>{let max=match ty{Some(Ty::Str{max:Some(max),..})=>max,_=>0};ctx=Some(json!({"max_length":max}));format!("String should have at most {max} character{}",if max==1{""}else{"s"})},
   "too_long"=>{let max=match ty{Some(Ty::ListModel{max,..})=>max,_=>0};ctx=Some(json!({"field_type":"List","max_length":max,"actual_length":current.as_array().map(Vec::len)}));format!("List should have at most {max} items after validation, not {}",current.as_array().map_or(0,Vec::len))},
   _=>format!("Input is not valid ({})",e.ty),
  };
  let input=if e.ty=="missing"{parent}else{current};
  let mut out=json!({"type":kind,"loc":loc,"msg":message,"input":input});if let Some(ctx)=ctx{out["ctx"]=ctx}out
 }).collect())
}
