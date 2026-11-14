#!/usr/bin/env python3
"""Pair the existing Mac/iPhone SMS service with one Concierge workspace.

Only outbound HTTPS. Never scans historical SMS. Sends use the
already-installed native preview/confirmation bridge; no approval bypass.

Business/personal separation happens here, on the Mac, before anything leaves it
(see BusinessFilter). On a shared personal number only texts from numbers that
are NOT in the owner's Contacts are business enquiries; saved contacts, group
chats, short codes and verification codes never leave the Mac. The owner can
override per number with ~/.concierge/sms_filter.json or:
  mac_sms_agent.py --mark personal +6421...   /  --mark business +6421...
  mac_sms_agent.py --dry-run 7               (counts only, nothing sent)
"""
import argparse
import glob
import hashlib
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


FILTER_PATH = "~/.concierge/sms_filter.json"
ADDRESS_BOOKS = "~/Library/Application Support/AddressBook/**/AddressBook-v22.abcddb"
DEFAULT_FILTER = {
    # Numbers that are always personal (never forwarded, never texted by the platform).
    "personal": [],
    # Numbers that are always business, even if saved in Contacts.
    "business": [],
    # A saved contact can opt a single text in by starting it with one of these words (e.g. "BIZ").
    "business_keywords": [],
    # iMessage from unknown numbers. Off by default: the connector historically read SMS only.
    "include_imessage": False,
}


def to_e164(value, country_code):
    """Contacts store numbers as typed ('021 555 0123'); match them in E.164 like chat.db does."""
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        pass
    elif raw.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = country_code + digits[1:]
    elif not digits.startswith(country_code) and len(digits) <= 10:
        digits = country_code + digits
    return "+"+digits if 7 <= len(digits) <= 15 else ""


def sender_hash(number):
    return hashlib.sha256(number.encode()).hexdigest()[:10]


class BusinessFilter:
    """Decides, on the Mac, whether an incoming text is a business enquiry.

    Fails closed: if Contacts cannot be read, nothing is forwarded (a personal text reaching the CRM and
    getting an AI reply is worse than a business text waiting for the owner to fix a permission).
    """

    def __init__(self, own_number, path=FILTER_PATH, address_books=ADDRESS_BOOKS, refresh=300):
        self.own = own_number
        self.country = "64" if own_number.startswith("+64") else re.sub(r"\D", "", own_number)[:2]
        self.path = Path(path).expanduser()
        self.address_books = address_books
        self.refresh = refresh
        self.loaded_at = None
        self.contacts = None
        self.settings = dict(DEFAULT_FILTER)

    def load(self, force=False):
        if not force and self.loaded_at is not None and time.monotonic()-self.loaded_at < self.refresh:
            return
        settings = dict(DEFAULT_FILTER)
        if self.path.exists():
            settings.update(json.loads(self.path.read_text()))
        for key in ("personal", "business"):
            settings[key] = {to_e164(n, self.country) for n in settings.get(key, []) if to_e164(n, self.country)}
        settings["business_keywords"] = [k.strip().lower() for k in settings.get("business_keywords", []) if k.strip()]
        self.settings = settings
        self.contacts = self.read_contacts()
        self.loaded_at = time.monotonic()

    def read_contacts(self):
        if isinstance(self.address_books, (set, frozenset)):
            return {to_e164(n, self.country) for n in self.address_books} - {""}
        numbers, readable = set(), False
        for book in glob.glob(str(Path(self.address_books).expanduser()), recursive=True):
            try:
                with sqlite3.connect("file:"+book+"?mode=ro", uri=True, timeout=3) as c:
                    rows = c.execute("SELECT ZFULLNUMBER FROM ZABCDPHONENUMBER").fetchall()
                readable = True
            except sqlite3.Error:
                continue
            numbers.update(to_e164(r[0], self.country) for r in rows)
        return (numbers - {""}) if readable else None

    def decide(self, sender, text, group=False, raw_sender=""):
        """Returns (forward, reason). Reasons are safe to log; they never include the number or text."""
        self.load()
        if not sender:
            return False, "short_code_or_name"
        if sender == self.own:
            return False, "own_number"
        if group:
            return False, "group_chat"
        if not text:
            return False, "no_text"
        if authentication_message(text):
            return False, "verification_code"
        if sender in self.settings["personal"]:
            return False, "marked_personal"
        if sender in self.settings["business"]:
            return True, "marked_business"
        if self.contacts is None:
            return False, "contacts_unreadable"
        if sender in self.contacts:
            first = text.strip().split(None, 1)[0].lower().strip(":,.-") if text.strip() else ""
            if first and first in self.settings["business_keywords"]:
                return True, "contact_keyword"
            return False, "saved_contact"
        return True, "unknown_number"

    def may_text(self, recipient, forwarded):
        """The platform may only text people whose texts we forwarded, or numbers that are not personal."""
        self.load()
        if recipient in forwarded or recipient in self.settings["business"]:
            return True
        if recipient in self.settings["personal"]:
            return False
        if self.contacts is None:
            return False
        return recipient not in self.contacts

    def mark(self, kind, number):
        data = dict(DEFAULT_FILTER)
        if self.path.exists():
            data.update(json.loads(self.path.read_text()))
        n = to_e164(number, self.country)
        if not n:
            raise ValueError("Not a phone number")
        for other in ("personal", "business"):
            if other != kind:
                data[other] = [x for x in data.get(other, []) if to_e164(x, self.country) != n]
        if kind in ("personal", "business") and n not in {to_e164(x, self.country) for x in data.get(kind, [])}:
            data[kind] = list(data.get(kind, [])) + [n]
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2)+"\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        self.loaded_at = None
        return n


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
            "CREATE TABLE IF NOT EXISTS forwarded(sender TEXT PRIMARY KEY,last_at INTEGER);"
        )
        self.filter = BusinessFilter(config["from_number"], config.get("filter_path", FILTER_PATH),
                                     config.get("address_books", ADDRESS_BOOKS))
        self.skipped = {}
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
        forwarded = {r[0] for r in self.journal.execute("SELECT sender FROM forwarded")}
        if not self.filter.may_text(job["recipient"], forwarded):
            # A personal contact must never receive a platform text from the owner's own number.
            self.journal.execute("INSERT INTO sends(id,status,receipt) VALUES(?,'failed','')",(ident,))
            self.journal.commit()
            print("Phone SMS job refused: personal recipient", sender_hash(job["recipient"]), flush=True)
            return ("failed","")
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

    def candidates(self, after_row=None, since_seconds=None, limit=100):
        """Incoming texts on this line, with whether each came through a group chat."""
        services = ("SMS", "iMessage") if self.filter.settings.get("include_imessage") else ("SMS",)
        with self.database() as c:
            has_chats = c.execute("SELECT 1 FROM sqlite_master WHERE name='chat_message_join'").fetchone()
            group = ("(SELECT MAX(CASE WHEN ch.style=43 THEN 1 ELSE 0 END) FROM chat_message_join j "
                     "JOIN chat ch ON ch.ROWID=j.chat_id WHERE j.message_id=m.ROWID)") if has_chats else "0"
            where, args = ["m.is_from_me=0", "m.service IN (%s)" % ",".join("?"*len(services))], list(services)
            if after_row is not None:
                where.append("m.ROWID>?"); args.append(after_row)
            if since_seconds is not None:
                # chat.db dates are nanoseconds since 2001-01-01.
                where.append("m.date>?"); args.append(int((time.time()-978307200-since_seconds)*1e9))
            sql = ("SELECT m.ROWID,m.guid,h.id,m.text,m.destination_caller_id,"+group+" FROM message m "
                   "JOIN handle h ON h.ROWID=m.handle_id WHERE "+" AND ".join(where)+" ORDER BY m.ROWID")
            if limit:
                sql += " LIMIT %d" % limit
            return c.execute(sql, args).fetchall()

    def classify(self, sender_raw, text, line, group):
        if normalize(line) != self.config["from_number"]:
            return None, "other_line"
        sender = to_e164(sender_raw, self.filter.country) if re.search(r"\d{7}", re.sub(r"\D", "", sender_raw or "")) else ""
        return sender, self.filter.decide(sender, text, bool(group))[1]

    def inbound(self):
        self.filter.load()
        current = self.journal.execute("SELECT value FROM cursor WHERE name='sms'").fetchone()
        if current is None:
            self.journal.execute("INSERT INTO cursor VALUES('sms',?)",(self.baseline(),))
            self.journal.commit()
            return 0
        count = 0
        for row_id,guid,sender_raw,text,line,group in self.candidates(after_row=current[0]):
            sender, reason = self.classify(sender_raw, text, line, group)
            if reason in ("unknown_number", "marked_business", "contact_keyword") and guid:
                self.api("/inbound",{"message_id":guid,"sender":sender,"to":self.config["from_number"],"body":text[:1500]})
                self.journal.execute("INSERT OR REPLACE INTO forwarded VALUES(?,?)",(sender,int(time.time())))
                count+=1
            else:
                self.skipped[reason] = self.skipped.get(reason, 0)+1
                if sender and reason not in ("other_line", "own_number"):
                    # Counts and a one-way hash only: never the number or the words of a personal text.
                    print("Kept private:", reason, sender_hash(sender), flush=True)
            self.journal.execute("UPDATE cursor SET value=? WHERE name='sms'",(row_id,))
            self.journal.commit()
        return count

    def dry_run(self, days):
        self.filter.load(force=True)
        counts = {}
        for _row,_guid,sender_raw,text,line,group in self.candidates(since_seconds=days*86400, limit=0):
            reason = self.classify(sender_raw, text, line, group)[1]
            counts[reason] = counts.get(reason, 0)+1
        forward = sum(v for k, v in counts.items() if k in ("unknown_number", "marked_business", "contact_keyword"))
        return {"days": days, "forward": forward, "keep_private": sum(counts.values())-forward,
                "contacts_loaded": len(self.filter.contacts or ()) if self.filter.contacts is not None else "unreadable",
                "include_imessage": bool(self.filter.settings.get("include_imessage")), "by_reason": counts}

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
    p.add_argument("--dry-run",type=int,metavar="DAYS",help="count what would be forwarded; sends nothing")
    p.add_argument("--mark",nargs=2,metavar=("personal|business|clear","NUMBER"),help="mark a number personal or business")
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
    config=json.loads(path.read_text())
    if args.mark:
        kind,number=args.mark
        if kind not in ("personal","business","clear"):
            p.error("--mark takes personal, business or clear")
        n=BusinessFilter(config["from_number"],config.get("filter_path",FILTER_PATH)).mark(kind,number)
        print("Marked",kind,sender_hash(n),flush=True)
        return
    agent=PhoneAgent(config)
    if args.dry_run:
        print(json.dumps(agent.dry_run(args.dry_run)),flush=True)
        return
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
