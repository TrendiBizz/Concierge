#!/usr/bin/env python3
"""Pair the existing Mac/iPhone SMS service with one Concierge workspace.

Only outbound HTTPS. Never scans iMessage or historical SMS. Sends use the
already-installed native preview/confirmation bridge; no approval bypass.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.request
import uuid

NUMBER = re.compile(r"^\+[1-9]\d{6,14}$")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def normalize(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return "+"+digits if 7 <= len(digits) <= 15 else ""


def authentication_message(text):
    # Authentication traffic on the same SIM is not a customer enquiry.
    code=bool(re.search(r"\b\d{4,10}\b",text))
    context=bool(re.search(r"\b(?:verification|security|authentication|passcode|otp|2fa|login|sign.in|one.time)\b",text,re.I))
    do_not_share=bool(re.search(r"(?:do not|don't) share",text,re.I))
    authentication_code=bool(re.search(r'\b(?:code|otp|passcode|2fa)\b',text,re.I))
    return code and ((context and authentication_code) or (do_not_share and 'code' in text.lower()))


class PhoneAgent:
    def __init__(self, config):
        self.config = config
        self.base = config["url"].rstrip("/")
        if self.base != "https://concierge.trendibizz.com/api/v1/device-sms":
            raise ValueError("Use the verified Concierge device endpoint")
        if not NUMBER.fullmatch(config["from_number"]) or len(config["token"]) < 40:
            raise ValueError("Invalid paired-phone configuration")
        self.bridge = Path(config["bridge"]).expanduser()
        self.messages = Path(config.get("messages_db", "~/Library/Messages/chat.db")).expanduser()
        state = Path(config["state_dir"]).expanduser()
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.journal = sqlite3.connect(state/"device.sqlite")
        os.chmod(state/"device.sqlite", 0o600)
        self.journal.executescript(
            "CREATE TABLE IF NOT EXISTS sends(id TEXT PRIMARY KEY,status TEXT,receipt TEXT,acked INTEGER DEFAULT 0);"
            "CREATE TABLE IF NOT EXISTS cursor(name TEXT PRIMARY KEY,value INTEGER);"
        )
        self.http = urllib.request.build_opener(NoRedirect)

    def api(self, path, payload):
        req = urllib.request.Request(self.base+path,
            data=json.dumps(payload).encode(), method="POST",
            headers={"Authorization":"Bearer "+self.config["token"],"Content-Type":"application/json",
                     "User-Agent":"TrendiPhoneConnector/1.0"})
        with self.http.open(req, timeout=45) as response:
            return json.load(response)

    def bridge_request(self, action, params):
        ident = str(uuid.uuid4())
        request = self.bridge/"control/requests"/("request-"+ident+".json")
        response = self.bridge/"control/responses"/("response-"+ident+".json")
        # Publish atomically so launchd cannot consume a partial JSON request.
        temporary = request.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,"w") as output:
            json.dump({"id":ident,"action":action,"params":params},output)
        os.replace(temporary,request)
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            if response.exists():
                data = json.loads(response.read_text())
                response.unlink()
                if data.get("id") != ident:
                    raise ValueError("Bridge response identity mismatch")
                return data
            time.sleep(.25)
        raise TimeoutError("Native Messages confirmation/bridge timed out")

    def database(self):
        return sqlite3.connect("file:"+str(self.messages)+"?mode=ro",uri=True,timeout=3)

    def baseline(self):
        with self.database() as c:
            return c.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0]

    def verified_receipt(self, baseline, recipient, body):
        """Match this exact new SMS, recipient and SIM line; not another send."""
        with self.database() as c:
            rows = c.execute(
                "SELECT m.guid,m.is_sent,m.error,m.destination_caller_id FROM message m "
                "JOIN handle h ON h.ROWID=m.handle_id WHERE m.ROWID>? AND m.is_from_me=1 "
                "AND m.service='SMS' AND h.id=? AND m.text=? ORDER BY m.ROWID DESC LIMIT 10",
                (baseline,recipient,body),
            ).fetchall()
        for guid,sent,error,line in rows:
            if normalize(line)!=self.config["from_number"]:
                continue
            if error:
                return "failed",""
            if sent and guid:
                return "sent",guid
        return "uncertain",""

    def send(self, job):
        ident = str(uuid.UUID(job["id"]))
        previous = self.journal.execute("SELECT status,receipt FROM sends WHERE id=?",(ident,)).fetchone()
        if previous:
            return ("uncertain","") if previous[0]=="started" else previous
        if (job.get("from_number")!=self.config["from_number"]
                or not NUMBER.fullmatch(job.get("recipient",""))
                or not isinstance(job.get("body"),str) or not 1<=len(job["body"])<=1500):
            raise ValueError("Phone job failed identity/content checks")
        self.journal.execute("INSERT INTO sends(id,status,receipt) VALUES(?,'started','')",(ident,))
        self.journal.commit()
        result = ("uncertain","")
        try:
            baseline = self.baseline()
            params = {"to":job["recipient"],"text":job["body"],"service":"SMS"}
            preview = self.bridge_request("send_preview",params)
            if not preview.get("ok") or not preview.get("send_nonce"):
                result = ("failed","")
            else:
                sent = self.bridge_request("send",{**params,"send_nonce":preview["send_nonce"]})
                if not sent.get("ok"):
                    result = ("failed","")
                else:
                    deadline = time.monotonic()+30
                    previous_receipt = ""
                    while time.monotonic()<deadline:
                        result = self.verified_receipt(baseline,job["recipient"],job["body"])
                        if result[0]=="failed" or (result[0]=="sent" and result[1]==previous_receipt):
                            break
                        previous_receipt=result[1]
                        time.sleep(1.5)
                    else:
                        result=("uncertain","")
        finally:
            self.journal.execute("UPDATE sends SET status=?,receipt=? WHERE id=?",(*result,ident))
            self.journal.commit()
        return result

    def inbound(self):
        current = self.journal.execute("SELECT value FROM cursor WHERE name='sms'").fetchone()
        if current is None:
            self.journal.execute("INSERT INTO cursor VALUES('sms',?)",(self.baseline(),))
            self.journal.commit()
            return 0
        with self.database() as c:
            rows = c.execute(
                "SELECT m.ROWID,m.guid,h.id,m.text,m.destination_caller_id FROM message m "
                "JOIN handle h ON h.ROWID=m.handle_id WHERE m.ROWID>? AND m.is_from_me=0 "
                "AND m.service='SMS' ORDER BY m.ROWID LIMIT 100",(current[0],),
            ).fetchall()
        count = 0
        for row_id,guid,sender,text,line in rows:
            sender=normalize(sender)
            if (normalize(line)==self.config["from_number"] and sender and
                    sender!=self.config["from_number"] and text and guid and not authentication_message(text)):
                self.api("/inbound",{"message_id":guid,"sender":sender,"to":self.config["from_number"],"body":text[:1500]})
                count+=1
            self.journal.execute("UPDATE cursor SET value=? WHERE name='sms'",(row_id,))
            self.journal.commit()
        return count

    def once(self):
        # Send receipts left by a previous run before accepting another job.
        for ident,status,receipt in self.journal.execute("SELECT id,status,receipt FROM sends WHERE acked=0").fetchall():
            if status=="started":
                status,receipt="uncertain",""
            self.api("/receipt",{"job_id":ident,"status":status,"receipt":receipt})
            self.journal.execute("UPDATE sends SET acked=1 WHERE id=?",(ident,));self.journal.commit()
        self.inbound()
        job=self.api("/poll",{}).get("job")
        if job:
            try:
                status,receipt=self.send(job)
            except Exception:
                status,receipt="uncertain",""
            self.api("/receipt",{"job_id":job["id"],"status":status,"receipt":receipt})
            self.journal.execute("UPDATE sends SET acked=1 WHERE id=?",(job["id"],));self.journal.commit()
            print("Phone SMS job completed:",status,flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument("--config");p.add_argument("--once",action="store_true");p.add_argument("--probe",action="store_true")
    args=p.parse_args()
    if args.probe:
        try:
            with sqlite3.connect('file:'+str(Path.home()/'Library/Messages/chat.db')+'?mode=ro',uri=True) as c:
                c.execute('SELECT MAX(ROWID) FROM message').fetchone()
            print('PASS background phone connector receipt access',flush=True)
            return
        except sqlite3.Error:
            raise SystemExit('Full Disk Access is required for the background phone connector')
    if not args.config:
        p.error('--config is required unless running --probe')
    path=Path(args.config)
    if path.stat().st_mode&0o077:
        raise SystemExit("Phone configuration must be private (chmod 600)")
    agent=PhoneAgent(json.loads(path.read_text()))
    while True:
        try:
            agent.once()
        except Exception as error:
            # Neither message contents, recipients nor authentication tokens in logs.
            print("Phone connector requires attention:",type(error).__name__,flush=True)
            if args.once:
                raise SystemExit(1)
        if args.once:
            return
        time.sleep(3)


if __name__=="__main__":
    main()
