"""Privacy-minimising operational logs and optional exception aggregation."""
import contextvars
import json
import logging
import os
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

request_id = contextvars.ContextVar('request_id', default='')


def safe_id(value):
    value = str(value) if value is not None else ''
    return value if re.fullmatch(r'[0-9a-fA-F-]{1,36}', value) else None


class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Do not forward arbitrary messages, URLs, payloads or exception strings:
        # existing libraries can include credentials and customer content in them.
        return json.dumps({
            'timestamp': self.formatTime(record), 'level': record.levelname,
            'logger': record.name, 'request_id': request_id.get(),
            'event': getattr(record, 'event', 'application_log'),
            'source': f'{record.module}:{record.lineno}',
            'tenant_id': safe_id(getattr(record, 'tenant_id', None)),
            'call_id': safe_id(getattr(record, 'call_id', None)),
            'status': getattr(record, 'status', None),
            'duration_ms': getattr(record, 'duration_ms', None),
            'exception_type': record.exc_info[0].__name__ if record.exc_info else None,
        })


def scrub_event(event, hint):
    exceptions = []
    for value in event.get('exception', {}).get('values', []):
        frames = [{key: frame[key] for key in ('module', 'function', 'lineno') if key in frame}
                  for frame in value.get('stacktrace', {}).get('frames', [])]
        exceptions.append({'type': value.get('type', 'Exception'),
                           'value': 'Unhandled API exception', 'stacktrace': {'frames': frames}})
    return {'event_id': event.get('event_id'), 'level': 'error',
            'message': 'Unhandled API exception', 'exception': {'values': exceptions},
            'tags': {'request_id': request_id.get()}}


def configure():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger().handlers[:] = [handler]
    logging.getLogger().setLevel(logging.INFO)
    # Disabled unless explicitly configured. Never send request bodies, local
    # variables, breadcrumbs or user identifiers to the third party.
    dsn = os.getenv('SENTRY_DSN', '')
    if dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=dsn, send_default_pii=False, include_local_variables=False,
                            default_integrations=False, traces_sample_rate=0,
                            before_send=scrub_event)
        except ImportError:
            logging.getLogger(__name__).warning('Error reporting SDK unavailable')


class RequestTelemetry(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        candidate = request.headers.get('x-request-id', '')
        correlation = candidate if re.fullmatch(r'[A-Za-z0-9_-]{8,64}', candidate) else uuid.uuid4().hex
        token = request_id.set(correlation)
        start = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers['X-Request-ID'] = correlation
            return response
        except Exception:
            if os.getenv('SENTRY_DSN'):
                try:
                    import sentry_sdk
                    sentry_sdk.capture_exception()
                except ImportError:
                    pass
            logging.getLogger(__name__).exception('request_failed')
            raise
        finally:
            logging.getLogger(__name__).info('request_complete', extra={
                'event': 'request_complete', 'status': status,
                'duration_ms': round((time.monotonic() - start) * 1000, 2),
            })
            request_id.reset(token)
