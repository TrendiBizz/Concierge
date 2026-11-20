"""Refresh only contact fixtures from the canonical Python implementation."""
import importlib.util
import json
import random
from pathlib import Path
root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("canonical_contact", root / "api/app/contact.py")
contact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contact)
path = Path(__file__).with_name("vectors.json")
fixture = json.loads(path.read_text())
old = fixture["contact"]
for case in old:
    case.update(phone=contact.normalize_phone(case["v"],case["cc"]), key=contact.contact_key(case["v"],case["cc"]),email=contact.is_email(case["v"]))
rng=random.Random(20261120)
values=["021 123 456","+64 21 123 456","64 0 21 123 456","21123456","021123","letters021123456","+1234abc5678","+١٢٣٤٥٦٧٨٩","１２３４５６７８９０","", " Ann@Example.test "]
values += ["".join(rng.choice("0123456789") for _ in range(n)) for n in range(1,18) for _ in range(8)]
for cc in ("1","44","61","64","353","49","33","91","","999"," 64 "):
    for value in values:
        old.append({"v":value,"cc":cc,"phone":contact.normalize_phone(value,cc),"key":contact.contact_key(value,cc),"email":contact.is_email(value)})
# Stable regeneration, including existing legacy vectors without duplication.
fixture["contact"] = list({(case["v"],case["cc"]):case for case in old}.values())
path.write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+"\n")
print(f"{len(fixture['contact'])} canonical contact vectors")
