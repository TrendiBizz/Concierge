"""Verify all canonical app/static bytes in the built image before starting it."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
expected = {}
for folder in ('app', 'static'):
    for file in (root / 'api' / folder).rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
            expected[str(file.relative_to(root / 'api'))] = hashlib.sha256(file.read_bytes()).hexdigest()
program = """
import hashlib,json
from pathlib import Path
result={}
for folder in ('app','static'):
 for file in (Path('/srv')/folder).rglob('*'):
  if file.is_file() and '__pycache__' not in file.parts and file.suffix!='.pyc':
   result[str(file.relative_to('/srv'))]=hashlib.sha256(file.read_bytes()).hexdigest()
print(json.dumps(result))
"""
result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                         '--entrypoint', 'python', sys.argv[1] if len(sys.argv) > 1 else 'concierge-api:trendi-local', '-c', program],
                        capture_output=True, text=True, check=True)
actual = json.loads(result.stdout)
if actual != expected:
    changed = sorted(k for k in expected.keys() | actual.keys() if expected.get(k) != actual.get(k))
    raise SystemExit('Image source mismatch: ' + ', '.join(changed))
print(f'Verified {len(expected)} current source files in the local API image.')
