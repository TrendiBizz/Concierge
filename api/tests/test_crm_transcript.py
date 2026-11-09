import asyncio
import uuid
from unittest.mock import AsyncMock
from types import SimpleNamespace
import httpx
from app.main import app
from app import owner_auth, db


def test_crm_transcript_is_accessible_from_enquiry_and_scoped_to_owner_tenant(monkeypatch):
    tenant=uuid.uuid4();lead=uuid.uuid4()
    pool=SimpleNamespace(fetchval=AsyncMock(return_value=True),fetch=AsyncMock(return_value=[{'role':'user','content':'Please send me the details'}]))
    monkeypatch.setattr(db,'pool',lambda:pool)
    async def auth():return {'tenant_id':tenant,'role':'owner'}
    app.dependency_overrides[owner_auth.current_user]=auth
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://test') as c:
            return await c.get(f'/owner/crm/leads/{lead}/transcript')
    try:
        result=asyncio.run(run())
        assert result.status_code==200
        assert result.json()[0]['content']=='Please send me the details'
        assert pool.fetch.await_args.args[1:]==(tenant,lead)
        pool.fetchval.return_value=False;pool.fetch.reset_mock()
        assert asyncio.run(run()).status_code==404
        pool.fetch.assert_not_awaited()
    finally:app.dependency_overrides.clear()
