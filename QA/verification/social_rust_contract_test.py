"""Cross-repository, real HTTP contract test for Concierge -> Rust Social.

Only disposable local SQLite and fake social credentials are used. The Rust
publisher is disabled and no social network request is possible.
"""
import asyncio
import base64
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from app import social_bridge

RUST = Path("/Users/jo/work-staging/trendi-site/concierge-stack/social-service")
BINARY = RUST / "target/debug/concierge-social"
HOST = "http://127.0.0.1:4390"


def available():
    with socket.socket() as client:
        return client.connect_ex(("127.0.0.1", 4390)) != 0


async def contract(key):
    tenant = {"slug": "isolated-social-test", "name": "Isolated Social Test",
              "tenant_id": "only-test", "role": "owner"}
    config = SimpleNamespace(social_service_enabled=True,
                             social_service_url=HOST, social_concierge_key=key)
    with patch.object(social_bridge, "get_settings", return_value=config):
        result = await social_bridge.accounts(tenant)
        assert result == [], result

        # Use only fake account credentials; publisher is explicitly disabled.
        fake = await social_bridge._request("POST",
            "/v1/customers/isolated-social-test/accounts", {
                "network": "bluesky", "external_id": "test.invalid",
                "display_name": "Not a real social account",
                "access_token": "offline_fake_credential_never_used",
                "refresh_token": None,
            })
        aid = fake["id"]
        draft = await social_bridge.create_draft(tenant, "Safe test social draft",
                                                  [aid], hashtags="#offline")
        assert draft["status"] == "draft", draft
        submitted = await social_bridge.submit_draft(tenant, draft["id"])
        assert submitted["status"] == "pending_approval", submitted
        approval = await social_bridge.request_approval(
            tenant, draft["id"], int(time.time()))
        assert approval["exact_text"] == "Safe test social draft\n#offline", approval
        decided = await social_bridge.decide(tenant, approval["token"], True)
        assert decided["status"] == "scheduled", decided
        posts = await social_bridge.posts(tenant)
        assert len(posts) == 1 and posts[0]["status"] == "scheduled", posts
        try:
            await social_bridge.decide(tenant, approval["token"], True)
        except Exception:
            pass
        else:
            raise AssertionError("Double-approval was accepted")
        print("CROSS_REPO_HTTP_CONTRACT_PASS: customer isolation, account, draft, submit, one-use approval")


def main():
    if not BINARY.is_file():
        raise RuntimeError("Build Rust binary with cargo build before running the contract test")
    if not available():
        raise RuntimeError("Port 4390 already in use; do not modify the running service")
    with tempfile.TemporaryDirectory(prefix="trendi-social-contract-") as directory:
        key = secrets.token_hex(32)
        env = {
            **os.environ,
            "SOCIAL_CONCIERGE_KEY": key,
            "SOCIAL_AGENT_KEY": secrets.token_hex(32),
            "SOCIAL_VAULT_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
            "SOCIAL_DB": str(Path(directory) / "social.db"),
            "SOCIAL_BIND": "127.0.0.1:4390",
            "SOCIAL_ENABLE_PUBLISH": "false",
        }
        with open(Path(directory) / "server.log", "w") as log:
            process = subprocess.Popen([str(BINARY)], env=env,
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(60):
                    if process.poll() is not None:
                        raise RuntimeError("Rust service unexpectedly exited")
                    try:
                        if httpx.get(HOST + "/health", timeout=0.3).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Rust service never became healthy")
                asyncio.run(contract(key))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


if __name__ == "__main__":
    main()
