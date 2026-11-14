import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import uuid

spec=importlib.util.spec_from_file_location("mac_sms_agent",Path(__file__).parents[1]/"mac_sms_agent.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class PhoneAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/'messages.sqlite'
        c=sqlite3.connect(self.db)
        c.executescript("CREATE TABLE handle(id TEXT);CREATE TABLE message(guid TEXT,is_sent INTEGER,error INTEGER,destination_caller_id TEXT,handle_id INTEGER,is_from_me INTEGER,service TEXT,text TEXT);")
        c.execute("INSERT INTO handle VALUES('+64215550123')");c.commit();c.close()
        self.agent=module.PhoneAgent({'url':'https://concierge.trendibizz.com/api/v1/device-sms',
            'token':'t'*48,'from_number':'+64278817368','bridge':str(self.root),
            'messages_db':str(self.db),'state_dir':str(self.root/'state'),
            'filter_path':str(self.root/'filter.json'),'address_books':frozenset()})
        self.calls=[];self.agent.api=lambda path,payload:self.calls.append((path,payload)) or {'job':None}

    def tearDown(self):
        self.agent.journal.close();self.tmp.cleanup()

    def add(self,service='SMS',line='+64278817368',text='Business question',outgoing=0,sent=1,error=0,handle=1):
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO message(guid,is_sent,error,destination_caller_id,handle_id,is_from_me,service,text) VALUES(?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),sent,error,line,handle,outgoing,service,text))

    def handle(self,number):
        with sqlite3.connect(self.db) as c:
            return c.execute("INSERT INTO handle VALUES(?)",(number,)).lastrowid

    def use_filter(self,contacts=(),**settings):
        self.agent.filter.address_books=frozenset(contacts)
        (self.root/'filter.json').write_text(json.dumps(settings))
        self.agent.filter.loaded_at=None

    def test_history_is_not_imported_and_only_new_business_sms_is_forwarded(self):
        self.add();self.agent.inbound();self.assertEqual(self.calls,[])
        self.add(service='iMessage',text='Private iMessage')
        self.add(line='+64215559999',text='Other SIM')
        self.add(outgoing=1,text='Own sent message')
        self.add(text='New business SMS')
        self.assertEqual(self.agent.inbound(),1)
        self.assertEqual(self.calls[0][1]['body'],'New business SMS')
        self.assertEqual(self.agent.inbound(),0)

    def test_receipt_requires_exact_new_sms_recipient_text_line_and_sent_status(self):
        self.add(text='Exact',outgoing=1)
        baseline=self.agent.baseline()
        self.add(service='iMessage',text='Exact',outgoing=1)
        self.add(line='+64215559999',text='Exact',outgoing=1)
        self.add(text='Other body',outgoing=1)
        self.assertEqual(self.agent.verified_receipt(baseline,'+64215550123','Exact')[0],'uncertain')
        self.add(text='Exact',outgoing=1,sent=0)
        self.assertEqual(self.agent.verified_receipt(baseline,'+64215550123','Exact')[0],'uncertain')
        self.add(text='Exact',outgoing=1)
        self.assertEqual(self.agent.verified_receipt(baseline,'+64215550123','Exact')[0],'sent')

    def test_errors_are_never_reported_sent(self):
        self.add(text='Exact',outgoing=1,error=42)
        self.assertEqual(self.agent.verified_receipt(0,'+64215550123','Exact')[0],'failed')

    def test_interrupted_send_is_not_replayed(self):
        ident=str(uuid.uuid4())
        self.agent.journal.execute("INSERT INTO sends(id,status,receipt) VALUES(?,'started','')",(ident,));self.agent.journal.commit()
        self.agent.bridge_request=lambda *args:(_ for _ in ()).throw(AssertionError('Must not send again'))
        self.assertEqual(self.agent.send({'id':ident}),('uncertain',''))
        self.agent.once()
        self.assertEqual(self.calls[0][1]['status'],'uncertain')
        self.calls.clear();self.agent.once()
        self.assertEqual([x for x in self.calls if x[0]=='/receipt'],[])

    def test_other_sender_is_rejected_before_any_bridge_request(self):
        with self.assertRaises(ValueError):
            self.agent.send({'id':str(uuid.uuid4()),'from_number':'+64215559999','recipient':'+64215550123','body':'test'})

    def test_heartbeat_identifies_the_connector_to_the_public_gateway(self):
        class Gateway:
            def open(inner, request, timeout):
                self.assertEqual(request.get_header('User-agent'), 'TrendiPhoneConnector/1.0')
                self.assertEqual(request.get_method(), 'POST')
                self.assertEqual(request.full_url, self.agent.base+'/poll')
                return io.BytesIO(b'{"job":null}')
        self.agent.http = Gateway()
        self.assertEqual(module.PhoneAgent.api(self.agent, '/poll', {}), {'job': None})

    def test_authentication_sms_is_not_sent_to_ai_or_crm(self):
        self.agent.inbound()
        self.add(text='Your login verification code is 123456. Do not share it.')
        self.add(text='Booking reference 123456: can you check my appointment?')
        self.add(text='Can you do a security review of port 8080?')
        self.agent.inbound()
        self.assertEqual(len(self.calls),2)
        self.assertTrue(self.calls[0][1]['body'].startswith('Booking reference'))

    def test_saved_contacts_stay_private_and_unknown_numbers_are_business(self):
        friend=self.handle('+64211112222');stranger=self.handle('+64213334444')
        self.use_filter(contacts={'021 111 2222'})
        self.agent.inbound()
        self.add(handle=friend,text='Dinner tonight?')
        self.add(handle=stranger,text='Can I get a quote for a deck?')
        self.assertEqual(self.agent.inbound(),1)
        self.assertEqual([c[1]['sender'] for c in self.calls],['+64213334444'])

    def test_marks_override_contacts_and_keywords_opt_in_one_text(self):
        friend=self.handle('+64211112222');stranger=self.handle('+64213334444')
        self.use_filter(contacts={'+64211112222'},personal=['+64213334444'],business_keywords=['biz'])
        self.agent.inbound()
        self.add(handle=stranger,text='Hi, personal really')
        self.add(handle=friend,text='Hello again')
        self.add(handle=friend,text='BIZ: my neighbour wants a quote')
        self.assertEqual(self.agent.inbound(),1)
        self.assertTrue(self.calls[0][1]['body'].startswith('BIZ'))
        self.agent.filter.mark('business','021 111 2222')
        self.add(handle=friend,text='Now a client')
        self.assertEqual(self.agent.inbound(),1)

    def test_short_codes_and_unreadable_contacts_never_forward(self):
        code=self.handle('2344');name=self.handle('ANZ')
        self.agent.inbound()
        self.add(handle=code,text='Your parcel is on its way');self.add(handle=name,text='Bank notice')
        self.assertEqual(self.agent.inbound(),0)
        self.agent.filter.address_books=str(self.root/'missing/*.abcddb');self.agent.filter.loaded_at=None
        self.add(text='Unknown sender while Contacts is unreadable')
        self.assertEqual(self.agent.inbound(),0)
        self.assertEqual(self.agent.skipped.get('contacts_unreadable'),1)

    def test_group_chats_are_private(self):
        with sqlite3.connect(self.db) as c:
            c.executescript("CREATE TABLE chat(style INTEGER);CREATE TABLE chat_message_join(chat_id INTEGER,message_id INTEGER);INSERT INTO chat VALUES(43);")
        self.agent.inbound()
        self.add(text='Group banter')
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO chat_message_join VALUES(1,(SELECT MAX(rowid) FROM message))")
        self.add(text='One to one enquiry')
        self.assertEqual(self.agent.inbound(),1)
        self.assertEqual(self.calls[0][1]['body'],'One to one enquiry')

    def test_platform_never_texts_a_personal_contact(self):
        self.use_filter(contacts={'+64211112222'})
        self.agent.bridge_request=lambda *a:(_ for _ in ()).throw(AssertionError('must not reach Messages'))
        job={'id':str(uuid.uuid4()),'from_number':'+64278817368','recipient':'+64211112222','body':'Thanks!'}
        self.assertEqual(self.agent.send(job),('failed',''))

    def test_dry_run_counts_without_sending(self):
        with sqlite3.connect(self.db) as c:
            c.execute("ALTER TABLE message ADD COLUMN date INTEGER DEFAULT 0")
        friend=self.handle('+64211112222')
        self.use_filter(contacts={'+64211112222'})
        now=int((module.time.time()-978307200)*1e9)
        self.add();self.add(handle=friend,text='Personal')
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE message SET date=?",(now,))
        result=self.agent.dry_run(7)
        self.assertEqual((result['forward'],result['keep_private']),(1,1))
        self.assertEqual(self.calls,[])

    def test_local_numbers_in_contacts_match_international_senders(self):
        self.assertEqual(module.to_e164('021 555 0123','64'),'+64215550123')
        self.assertEqual(module.to_e164('+61 412 345 678','64'),'+61412345678')
        self.assertEqual(module.to_e164('0064 21 555 0123','64'),'+64215550123')


if __name__=='__main__':unittest.main()
