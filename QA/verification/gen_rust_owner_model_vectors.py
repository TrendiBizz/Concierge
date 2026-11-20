"""Generate request-schema fixtures by running canonical Pydantic models.

No lifespan, DB or provider calls. Set a fake local environment before imports.
"""
import json
import os
import random
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
os.environ.update(DATABASE_URL="postgresql://unused:unused@127.0.0.1:1/unused",ADMIN_TOKEN="local-only",OUTBOX_ENABLED="false")
sys.path[:0]=[str(root/"QA/verification/shims"),str(root/"api")]
from app.products import ProductIn,StockAdjust
from app.main import TemplateBody,OwnerLogin,OwnerRedeem,OwnerLinkAccept,OwnerCodeVerify,CompanyBody,CompanyUpdate,Assignee,BulkAssign,plain_validation_message
from app.action_ops import AutomationBody,Action,Delivery,Bundle
from pydantic import ValidationError
models={"TemplateBody":TemplateBody,"CompanyBody":CompanyBody,"CompanyUpdate":CompanyUpdate,"Assignee":Assignee,"BulkAssign":BulkAssign,"ProductIn":ProductIn,"StockAdjust":StockAdjust,"OwnerLogin":OwnerLogin,"OwnerRedeem":OwnerRedeem,"OwnerLinkAccept":OwnerLinkAccept,"OwnerCodeVerify":OwnerCodeVerify,"ActionAutomation":AutomationBody,"CaseAction":Action,"CaseDelivery":Delivery,"CaseBundle":Bundle}
seeds={"TemplateBody":{"name":"Reply","subject":"Hello","body":"  Reply body  "},"CompanyBody":{"name":"Acme","domain":"example.test"},"CompanyUpdate":{"notes":"changed","parent_id":None},"Assignee":{"user_id":None},"BulkAssign":{"case_keys":["email:a@example.test"],"user_id":None},"ProductIn":{"sku":"A","name":"Test","sale_price_cents":1200},"StockAdjust":{"delta":1},"OwnerLogin":{"slug":"alpha","email":"a@example.test","password":"test password"},"OwnerRedeem":{"token":"t"*32,"password":"a test password"},"OwnerLinkAccept":{"token":"t"*32},"OwnerCodeVerify":{"email":"a@example.test","code":"123456"},"ActionAutomation":{"tenant_id":"11111111-1111-4111-8111-111111111111","paused":False},"CaseAction":{"op":"schedule_followup","idempotency_key":"key","dedupe_key":"dedupe","fingerprint":"fingerprint","case_version":12},"CaseDelivery":{"channel":"email","recipient":"a@example.test","body":"a reply","mode":"needs_approval","fingerprint":"fingerprint","dedupe_key":"key"},"CaseBundle":{"task_id":"task","tenant_id":"11111111-1111-4111-8111-111111111111"}}
rng=random.Random(20261120)
values=[None,True,False,0,1,-1,1.0,1.5,"","1","0","false","x"*321,[],{},"１２３４５６","١٢٣٤٥٦",100_000_001,-1_000_001]
fixtures=[]
for name,model in models.items():
    seed=seeds[name]
    cases=[seed,{},None,[],0,{**seed,"extra":True}]
    for field in model.model_fields:
        cases.append({k:v for k,v in seed.items() if k!=field})
        cases.extend({**seed,field:value} for value in values)
    for _ in range(50):
        cases.append({field:rng.choice(values) for field in model.model_fields if rng.random()<0.75})
    for body in cases:
        try:
            result=model.model_validate(body).model_dump(mode="json")
            fixtures.append({"model":name,"body":body,"result":result})
        except ValidationError as e:
            errors=[[".".join(map(str,error["loc"])),error["type"]] for error in e.errors()]
            # Pydantic's top-level model location is empty like the Rust port.
            fixtures.append({"model":name,"body":body,"errors":errors,"friendly":plain_validation_message(e.errors()),"full_errors":e.errors(include_url=False)})
out=root/"concierge-stack/core-rs/parity/owner_model_vectors.json"
out.write_text(json.dumps(fixtures,ensure_ascii=False,indent=2)+"\n")
print(f"{len(fixtures)} canonical request model vectors")
