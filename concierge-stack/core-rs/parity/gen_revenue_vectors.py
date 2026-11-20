"""Expected results from the real Python revenue implementation; no I/O."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "api"))
from app import revenue

rng = random.Random(20261120)
pairs = [(a,b) for a in (0,1,2,3,5,7,17,51,53,100,9999,-1) for b in (0,1,2,3,8,16,40,200,2000,-1)]
pairs += [(rng.randrange(10**12), rng.randrange(1,10**9)) for _ in range(500)]
cases = []
for i in range(300):
    def period():
        return {"enquiries": rng.randrange(1000), "by_channel": {c:rng.randrange(200) for c in revenue.CHANNELS},
                "quotes_sent":rng.randrange(2000), "quotes_accepted":rng.randrange(200),
                "accepted_cents":rng.randrange(10**12), "paid_cents":rng.randrange(10**12),
                "outstanding_cents":rng.randrange(10**12), "currency":rng.choice(["", "NZD", "AUD"])}
    current, previous = ({}, {}) if i == 0 else (period(), period())
    cases.append({"current":current,"previous":previous,"expected":revenue.build(current,previous)})
print(json.dumps({"arithmetic":[{"a":a,"b":b,"change":revenue.percent_change(a,b),"average":revenue.per_enquiry(a,b),"rate":revenue.convert_rate(a,b)} for a,b in pairs],"build":cases,"note":revenue.report.__doc__},indent=2))
