"""Private, repeatable configuration for the isolated local Trendi stack."""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / '.private/local-stack'
SITE = Path(os.environ.get('TRENDI_WEBSITE', str(ROOT.parent / 'trendi-site-web'))).resolve()
ORIGIN = 'http://127.0.0.1:8793'


def private_write(path, text):
    path.write_text(text)
    path.chmod(0o600)


def init():
    os.umask(0o077)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    PRIVATE.chmod(0o700)
    for required in ('site/index.html', 'deploy_known_good/_worker.js'):
        if not (SITE / required).is_file():
            raise SystemExit(f'Missing website source: {SITE / required}')
    path = PRIVATE / 'secrets.json'
    if not path.exists():
        private_write(path, json.dumps({
            'database': secrets.token_hex(24), 'admin': secrets.token_hex(32),
            'social': secrets.token_hex(32), 'agent': secrets.token_hex(32),
            'vault': base64.b64encode(secrets.token_bytes(32)).decode(),
        }))
    values = json.loads(path.read_text())
    api_path = PRIVATE / 'api.env'
    allowed = {'XAI_API_KEY', 'LLM_BASE_URL', 'LLM_API_KEY', 'CHAT_MODEL',
               'VOICE_MODEL', 'VOICE_DEFAULT'}
    if not api_path.exists():
        config = {
            'DATABASE_URL': f'postgresql://postgres:{values["database"]}@db:5432/trendi_local',
            'ADMIN_TOKEN': values['admin'], 'PUBLIC_BASE_URL': ORIGIN,
            'OWNER_PORTAL_URL': ORIGIN + '/owner-ui',
            'SOCIAL_SERVICE_ENABLED': 'true',
            'SOCIAL_SERVICE_URL': 'http://host.docker.internal:4391',
            'SOCIAL_CONCIERGE_KEY': values['social'],
            'OUTBOX_ENABLED': 'false', 'SMS_PROVIDER': 'none',
            'EMAIL_DRAFTS_ENABLED': 'true', 'PHONE_RECEPTIONIST_ENABLED': 'false',
            'PHONE_RECORDING_ENABLED': 'false', 'INBOUND_CLOUDFLARE_ENABLED': 'false',
            'OMP_NUM_THREADS': '1', 'TOKENIZERS_PARALLELISM': 'false',
            'HF_HUB_OFFLINE': '1',
        }
        # Reuse only the already configured AI endpoint. Never import databases,
        # social tokens, provider delivery credentials or outbox/CRM activation.
        previous = ROOT / '.private/oauth-staging/api.env'
        if previous.exists():
            for line in previous.read_text().splitlines():
                key, sep, value = line.partition('=')
                if sep and key in allowed:
                    config[key] = value
        private_write(api_path, ''.join(f'{k}={v}\n' for k, v in config.items()))
    config = dict(line.split('=', 1) for line in api_path.read_text().splitlines()
                  if '=' in line and not line.startswith('#'))
    if not (config.get('LLM_API_KEY') or config.get('XAI_API_KEY')):
        # The OAuth sandbox deliberately has no AI key. Reuse the existing
        # production text endpoint if available, without changing that service.
        result = subprocess.run(['docker', 'inspect', 'concierge-api-1'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            existing = dict(item.split('=', 1) for item in
                            json.loads(result.stdout)[0]['Config']['Env'] if '=' in item)
            if existing.get('LLM_API_KEY') or existing.get('XAI_API_KEY'):
                config.update({k: v for k, v in existing.items() if k in allowed})
                private_write(api_path, ''.join(f'{k}={v}\n' for k, v in config.items()))
    private_write(PRIVATE / 'postgres.env',
                  'POSTGRES_USER=postgres\nPOSTGRES_DB=trendi_local\n'
                  f'POSTGRES_PASSWORD={values["database"]}\n')
    private_write(PRIVATE / 'admin-token.txt', values['admin'] + '\n')
    render()
    print('Private local configuration ready; existing services unchanged.')
    print('Existing AI endpoint configured:', bool(config.get('LLM_API_KEY') or config.get('XAI_API_KEY')))


def render():
    runtime = PRIVATE / 'runtime.json'
    key = json.loads(runtime.read_text())['public_key'] if runtime.exists() else 'pk_local_pending'
    # Apply the marketing CSP only to marketing pages. The application provides
    # its own no-store/auth boundaries and contains existing inline UI scripts.
    global_headers = []
    for line in (SITE / 'site/_headers').read_text().splitlines()[1:]:
        if line and not line[0].isspace():
            break
        if ':' in line:
            name, value = line.strip().split(':', 1)
            if name != 'Strict-Transport-Security':
                value = value.strip().replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$')
                global_headers.append(f'add_header {name} "{value}" always;')
    text = (ROOT / 'scripts/local/nginx.conf').read_text()
    text = text.replace('__MARKETING_HEADERS__', '\n        '.join(global_headers))
    text = text.replace('__WIDGET_KEY__', key)
    private_write(PRIVATE / 'nginx.conf', text)


def social():
    values = json.loads((PRIVATE / 'secrets.json').read_text())
    binary = ROOT / 'concierge-stack/social-service/target/debug/concierge-social'
    pid_file = PRIVATE / 'social.pid'
    with socket.socket() as sock:
        occupied = sock.connect_ex(('127.0.0.1', 4391)) == 0
    if occupied:
        if not pid_file.exists():
            raise SystemExit('Port 4391 belongs to another process; leaving it unchanged.')
        pid = int(pid_file.read_text())
        command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                                 capture_output=True, text=True).stdout.strip()
        if command != str(binary):
            raise SystemExit('Local social process ownership could not be verified.')
        print('Owned local social service is already running.')
        return
    env = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'TMPDIR')}
    env.update(SOCIAL_CONCIERGE_KEY=values['social'], SOCIAL_AGENT_KEY=values['agent'],
               SOCIAL_VAULT_KEY=values['vault'], SOCIAL_DB=str(PRIVATE / 'social.db'),
               SOCIAL_BIND='127.0.0.1:4391', SOCIAL_ENABLE_PUBLISH='false')
    with (PRIVATE / 'social.log').open('ab') as log:
        process = subprocess.Popen([str(binary)], env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
    private_write(pid_file, str(process.pid))
    for _ in range(50):
        try:
            with urllib.request.urlopen('http://127.0.0.1:4391/health', timeout=1) as response:
                if response.status == 200:
                    print('Current Rust social code ready on private loopback port 4391.')
                    return
        except OSError:
            time.sleep(0.1)
    raise SystemExit('Local social startup failed; see the private social.log.')


if __name__ == '__main__':
    {'init': init, 'render': render, 'social': social}[sys.argv[1]]()
