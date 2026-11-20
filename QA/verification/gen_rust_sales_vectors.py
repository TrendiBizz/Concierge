"""Current canonical sales arithmetic, including aggregate values beyond bigint."""
import json,os,random,sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
os.environ.update(DATABASE_URL='postgresql://unused:unused@127.0.0.1:1/unused',ADMIN_TOKEN='local-only',OUTBOX_ENABLED='false')
sys.path[:0]=[str(root/'QA/verification/shims'),str(root/'api')]
from app import sales
rng=random.Random(20261120)
fixtures=[]
for count in (0,1,2,50,1000):
 for avg in (0,12500,2**63-1):
  rows=[{'status':rng.choice(sales.STAGES),'value_cents':rng.choice([0,1,2**63-1,rng.randrange(2**63)]),'name':str(i)} for i in range(count)]
  fixtures.append({'rows':rows,'avg':avg,'per':2,'forecast':sales.forecast(rows,avg,2)})
money=[]
for value in [0,-1,50,150,2**63-1,(2**63-1)*1000]+[rng.randrange(-2**73,2**73) for _ in range(100)]:money.append({'cents':str(value),'result':sales._money(value)})
(root/'concierge-stack/core-rs/parity/sales_current_vectors.json').write_text(json.dumps({'forecast':fixtures,'money':money},ensure_ascii=False,indent=2)+'\n')
print(f'{len(fixtures)} wide forecasts, {len(money)} money cases')
