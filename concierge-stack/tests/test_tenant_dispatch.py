"""Security regression tests for trusted voice dispatch."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from tenant_dispatch import DispatchDenied, VoiceBinding, issue, verify

SECRET = "sample-integration-test-dispatch-key-32-bytes"
A = VoiceBinding("customer_a", "+64210000001", "trunk_a", "call-a")
B = VoiceBinding("customer_b", "+64210000002", "trunk_b", "call-b")
REGISTRY = {
    A.destination: {"tenant_id": A.tenant_id, "trunk_id": A.trunk_id, "enabled": True,
                    "telephone_authorized": True, "provider_verified": True},
    B.destination: {"tenant_id": B.tenant_id, "trunk_id": B.trunk_id, "enabled": True,
                    "telephone_authorized": True, "provider_verified": True},
}


class DispatchTest(unittest.TestCase):
    def check(self, binding, envelope, registry=REGISTRY, now=200):
        return verify(envelope, binding.room, binding.destination, binding.trunk_id,
                      registry, SECRET, now)

    def test_both_tenants_valid(self):
        for binding in (A, B):
            with self.subTest(tenant=binding.tenant_id):
                self.assertEqual(binding, self.check(binding, issue(binding, SECRET, 100)))

    def test_tenant_swap_fails(self):
        self.assertRaises(DispatchDenied, self.check, B, issue(A, SECRET, 100))

    def test_room_destination_trunk_mismatch_fails(self):
        envelope = issue(A, SECRET, 100)
        for changed in (
            VoiceBinding(A.tenant_id, A.destination, A.trunk_id, "another-room"),
            VoiceBinding(A.tenant_id, B.destination, A.trunk_id, A.room),
            VoiceBinding(A.tenant_id, A.destination, B.trunk_id, A.room),
        ):
            with self.subTest(changed=changed):
                self.assertRaises(DispatchDenied, self.check, changed, envelope)

    def test_forged_claims_fail(self):
        envelope = issue(A, SECRET, 100)
        for key, value in (("tenant_id", B.tenant_id), ("issued_at", 199),
                           ("destination", B.destination), ("signature", "0" * 64)):
            changed = dict(envelope)
            changed[key] = value
            with self.subTest(key=key):
                self.assertRaises(DispatchDenied, self.check, A, changed)

    def test_expired_and_future_fails(self):
        self.assertRaises(DispatchDenied, self.check, A, issue(A, SECRET, 10))
        self.assertRaises(DispatchDenied, self.check, A, issue(A, SECRET, 201))

    def test_revocation_fails_after_signature(self):
        envelope = issue(A, SECRET, 100)
        for key in ("enabled", "telephone_authorized", "provider_verified"):
            registry = json.loads(json.dumps(REGISTRY))
            registry[A.destination][key] = False
            with self.subTest(key=key):
                self.assertRaises(DispatchDenied, self.check, A, envelope, registry)

    def test_registry_tenant_or_trunk_changed_fails(self):
        envelope = issue(A, SECRET, 100)
        for key, value in (("tenant_id", B.tenant_id), ("trunk_id", B.trunk_id)):
            registry = json.loads(json.dumps(REGISTRY))
            registry[A.destination][key] = value
            self.assertRaises(DispatchDenied, self.check, A, envelope, registry)

    def test_missing_and_malformed_fails(self):
        for envelope in ("", "{}", "[]", "{bad", None, {"v": 1}, []):
            with self.subTest(envelope=envelope):
                self.assertRaises(DispatchDenied, self.check, A, envelope)

    def test_weak_signing_key_fails(self):
        self.assertRaises(DispatchDenied, issue, A, "weak", 100)
        self.assertRaises(DispatchDenied, verify, issue(A, SECRET, 100), A.room,
                          A.destination, A.trunk_id, REGISTRY, "weak", 200)


if __name__ == "__main__":
    unittest.main()
