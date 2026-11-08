"""Build the reviewed local companion; does not grant permissions or start it."""
from pathlib import Path
import hashlib
import os
import plistlib
import shutil
import subprocess

source=Path(__file__).resolve().parent
app=Path.home()/'Applications/Trendi Phone Connector.app'
if app.exists() and (app/'Contents/Info.plist').exists():
    existing=plistlib.loads((app/'Contents/Info.plist').read_bytes())
    if existing.get('CFBundleIdentifier')!='com.trendi.phoneconnector':
        raise SystemExit('An unrelated app already exists at the target path; preserve it.')
resources=app/'Contents/Resources';binary=app/'Contents/MacOS/TrendiPhoneConnector'
resources.mkdir(parents=True,exist_ok=True);binary.parent.mkdir(exist_ok=True)
script=resources/'mac_sms_agent.py';temporary=resources/'mac_sms_agent.new'
if temporary.exists():temporary.unlink()
shutil.copy2(source/'mac_sms_agent.py',temporary);temporary.chmod(0o500);os.replace(temporary,script)
digest=hashlib.sha256(script.read_bytes()).hexdigest()
subprocess.run(['clang','-Wno-deprecated-declarations',str(source/'mac_launcher.c'),
                '-DAPPROVED_SCRIPT_SHA256="'+digest+'"','-o',str(binary)],check=True)
binary.chmod(0o700)
with (app/'Contents/Info.plist').open('wb') as file:
    plistlib.dump({'CFBundleIdentifier':'com.trendi.phoneconnector','CFBundleName':'Trendi Phone Connector',
                  'CFBundleExecutable':'TrendiPhoneConnector','CFBundlePackageType':'APPL',
                  'CFBundleShortVersionString':'1.0','CFBundleVersion':'1','LSUIElement':True},file)
subprocess.run(['codesign','--force','--sign','-','--identifier','com.trendi.phoneconnector',str(app)],check=True)
subprocess.run(['codesign','--verify','--strict',str(app)],check=True)
print('Built and verified:',app)
