import importlib.util
import io
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
            'messages_db':str(self.db),'state_dir':str(self.root/'state')})
        self.calls=[];self.agent.api=lambda path,payload:self.calls.append((path,payload)) or {'job':None}

    def tearDown(self):
        self.agent.journal.close();self.tmp.cleanup()

    def add(self,service='SMS',line='+64278817368',text='Business question',outgoing=0,sent=1,error=0):
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO message VALUES(?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),sent,error,line,1,outgoing,service,text))

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


if __name__=='__main__':unittest.main()
