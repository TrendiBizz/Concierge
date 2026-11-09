// Read-only Twenty compatibility probe. No customer records are printed or modified.
import { execFileSync } from 'node:child_process';
const key = execFileSync('security', ['find-generic-password', '-s', 'concierge-twenty-api-key', '-w'], {encoding:'utf8', stdio:['ignore','pipe','ignore']}).trim();
const base='http://127.0.0.1:3010';
const filters=[
 'and(phones.primaryPhoneNumber[eq]:"999999999999",phones.primaryPhoneCallingCode[eq]:"+64")',
 'emails.primaryEmail[eq]:"compatibility-probe.invalid@example.invalid"'
];
for(const filter of filters) {
 const r=await fetch(base+'/rest/people?limit=2&filter='+encodeURIComponent(filter),{headers:{authorization:'Bearer '+key,accept:'application/json'},signal:AbortSignal.timeout(7000)});
 const j=await r.json().catch(()=>null);
 const data=j?.data;
 const rows=data?.people;
 console.log(JSON.stringify({kind:filter.startsWith('and(')?'phone_composite':'email',status:r.status,hasData:!!data,isArray:Array.isArray(rows),count:Array.isArray(rows)?rows.length:null,errorCode:j?.error?.code||j?.statusCode||null}));
 if(!r.ok || !Array.isArray(rows))process.exitCode=1;
}
