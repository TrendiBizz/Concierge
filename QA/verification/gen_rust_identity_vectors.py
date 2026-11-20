"""Refresh conservative identity golden cases from the live Python module; no IO providers."""
import importlib.util
import json
import random
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'api'))
from app.identity import extract_details
rng = random.Random(20261120)
texts = [None, '', 'hello', "Hi it’s Sarah from Acme Plumbing", "my name is Sarah Jones", "I'm Interested", "Call me Ann", 'hello\nSarah', 'hello\nSarah 2', 'email A+tag@B.co.nz.', '021 555 1234', '+64 21 555 1234', '/0215551234/', 'from Acme Builders Ltd', 'Hutt Plumbing', 'Acme Engineering', 'I am Sarah from Acme Ltd, call +64215551234']
for _ in range(700):
    texts.append(rng.choice(['', 'hello ', "my name is ", "I'm ", 'from ', 'call me ']) + rng.choice(['Sarah', 'Looking', 'Ann Jones', 'Acme Ltd', 'Sarah-Jane', 'Élodie', '日本語', 'the plumbing']) + rng.choice(['', '\nSarah', ' 0215551234', ' +64215551234', ' a@b.co', ' /12345678/', '\r\n']))
cases=[{'text': t or '', 'cc': cc, 'allow_phone': phone, 'out': extract_details(t, cc, allow_phone=phone)} for t in texts for cc in ['', '64', '1'] for phone in [True, False]]
(ROOT/'concierge-stack/core-rs/parity/identity_vectors.json').write_text(json.dumps(cases, ensure_ascii=False, separators=(',', ':'))+'\n')
print(len(cases))
