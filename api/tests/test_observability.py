import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.observability import JsonFormatter, RequestTelemetry, request_id


def test_logs_exclude_customer_content_and_credentials():
    record = logging.LogRecord('test', logging.ERROR, '', 0, 'secret customer@example.com', (), None)
    output = JsonFormatter().format(record)
    assert 'secret' not in output
    assert 'customer@' not in output
    assert json.loads(output)['level'] == 'ERROR'


def test_request_correlation_validated_and_reset():
    app = FastAPI()
    app.add_middleware(RequestTelemetry)

    @app.get('/')
    def home():
        return {'request_id': request_id.get()}

    client = TestClient(app)
    response = client.get('/', headers={'X-Request-ID': 'safe-request-123'})
    assert response.json()['request_id'] == 'safe-request-123'
    assert response.headers['x-request-id'] == 'safe-request-123'
    response = client.get('/', headers={'X-Request-ID': 'customer@example.com'})
    assert len(response.headers['x-request-id']) == 32
    assert request_id.get() == ''


def test_public_status_reports_database_failure_without_details(monkeypatch):
    import asyncio
    from app.routers import public

    class Pool:
        async def fetchval(self, query):
            raise RuntimeError('secret database connection')

    monkeypatch.setattr(public.db, 'pool', lambda: Pool())
    response = asyncio.run(public.service_status())
    assert response.status_code == 503
    assert b'secret' not in response.body
    assert b'degraded' in response.body
    assert response.headers['cache-control'] == 'no-store'


def test_sentry_disabled_and_payload_allowlisted(monkeypatch):
    import sys
    import types
    from app.observability import configure
    calls = []
    monkeypatch.setitem(sys.modules, 'sentry_sdk', types.SimpleNamespace(init=lambda **kw: calls.append(kw)))
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    try:
        monkeypatch.delenv('SENTRY_DSN', raising=False)
        configure()
        assert not calls
        monkeypatch.setenv('SENTRY_DSN', 'https://example.invalid/1')
        configure()
        options = calls[0]
        assert options['send_default_pii'] is False
        assert options['include_local_variables'] is False
        event = options['before_send']({'event_id': '123', 'request': {'headers': {'Authorization': 'secret'}}, 'user': {'email': 'customer@example.com'}}, {})
        assert 'secret' not in json.dumps(event)
        assert 'customer@' not in json.dumps(event)
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)
