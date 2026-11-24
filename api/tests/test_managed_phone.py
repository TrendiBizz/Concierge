import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from app import managed_phone as m


def test_setup_rejects_injected_destinations_and_provider_secrets():
    for extra in ({'designated_number': 'sip:attacker@invalid'}, {'sip_password': 'secret'}, {'answer_mode': 'invalid'}):
        with pytest.raises(ValidationError):
            m.PhoneSetup(**{'designated_number': '+64275550123', 'owner_number': '+64275550123', **extra})


@pytest.mark.parametrize('role,code', [('viewer', 403), ('editor', 403), ('owner', 200)])
def test_owner_setup_is_tenant_scoped_and_cannot_activate_or_purchase(monkeypatch, role, code):
    import httpx
    from app.main import app
    from app import owner_auth
    identity = {'tenant_id': 'business-a', 'role': role}

    async def auth():
        return identity

    app.dependency_overrides[owner_auth.current_user] = auth
    write = AsyncMock(return_value={'status': 'requested'})
    monkeypatch.setattr(m, 'save_setup', write)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://testserver') as client:
            return await client.put('/owner/phone-setup', json={'designated_number': '+64275550123', 'owner_number': '+64275550123', 'connection': 'existing_sip'})
    try:
        result = asyncio.run(run())
        assert result.status_code == code
        if role == 'owner':
            assert write.await_args.args[0] == 'business-a'
        else:
            write.assert_not_awaited()
    finally:
        app.dependency_overrides.clear()


def test_new_service_purchase_is_not_a_setup_option():
    with pytest.raises(ValidationError):
        m.PhoneSetup(designated_number='+64275550123', owner_number='+64275550123', connection='buy_new_number')
