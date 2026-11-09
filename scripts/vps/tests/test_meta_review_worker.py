import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest

spec = importlib.util.spec_from_file_location("review_worker", Path(__file__).parents[1] / "meta-review-worker.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class ReviewSelectionTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("CREATE TABLE posts(id,customer_id,body,status,revision,approved_revision,scheduled_at); CREATE TABLE accounts(id,customer_id,network,needs_reauth);")
        self.db.executemany("INSERT INTO accounts VALUES(?,?,?,0)", [("review-fb", worker.CUSTOMER, "facebook"), ("review-x", worker.CUSTOMER, "x"), ("real-fb", "real-customer", "facebook")])

    def add(self, ident, customer=worker.CUSTOMER, account="review-fb", status="scheduled", revision=1, approved=1, due=5):
        self.db.execute("INSERT INTO posts VALUES(?,?,?,?,?,?,?)", (ident, customer, json.dumps({"customer_id":customer,"account_ids":[account]}), status, revision, approved, due))

    def test_approved_selected_post_only(self):
        self.add("yes")
        self.add("other", customer="real-customer", account="real-fb")
        self.add("cross-account", account="real-fb")
        self.add("unsupported", account="review-x")
        self.assertEqual(worker.select_due(self.db,10),["yes"])

    def test_draft_old_approval_and_future_are_excluded(self):
        self.add("draft", status="draft")
        self.add("old", revision=2, approved=1)
        self.add("future", due=100)
        self.assertEqual(worker.select_due(self.db,10),[])

    def test_processing_reconciles_without_replaying_published_jobs(self):
        self.add("pending",status="processing")
        self.add("done",status="published")
        self.assertEqual(worker.select_due(self.db,10),["pending"])

    def test_batch_is_bounded(self):
        for n in range(9):self.add(str(n))
        self.assertEqual(len(worker.select_due(self.db,10)),4)


if __name__ == "__main__":
    unittest.main()
