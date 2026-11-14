"""A configured business must not be greeted with its own setup wizard again.

ACME Ltd was already running — website, notifications, channels — and Studio still opened on
"1. Welcome / How Concierge works", which reads as "your setup did not save". The Permissions page
had the same problem in reverse: it explained the inbound email delivery chain to an owner who
has no way to act on it, so it is now a disclosure that opens itself only when a step is failing.
"""
from pathlib import Path

PORTAL = Path(__file__).resolve().parents[2] / "web" / "portal" / "src"


def test_setup_detects_an_already_configured_business():
    source = (PORTAL / "App.tsx").read_text()
    assert "const alreadySetUp = Boolean(business.name.trim() && business.site_url.trim());" in source
    # the welcome step is the thing that must not appear; editing must stay reachable
    assert "{step === 1 && !alreadySetUp ? (" in source
    assert "is set up</Heading>" in source
    assert 'label="Edit business details"' in source


def test_setup_and_permissions_live_under_settings_and_fold_away():
    """Available for changes, not waiting for attention once the business is installed."""
    app = (PORTAL / "App.tsx").read_text()
    # both are in the Settings group
    settings = app[app.index("group: 'Settings'"):]
    settings = settings[:settings.index("];")]
    assert "{tab: 'setup'" in settings
    assert "{tab: 'permissions', label: 'Channels and permissions'" in settings
    # and the group starts folded, so a finished install is not told to set anything up
    assert "const hidden = folded[group.group] ?? isSettings;" in app
    assert "localStorage.setItem('concierge:nav-folded'" in app
    # the ask still happens where the channel is used, for the first time
    assert "{tab === 'texts' ? <ChannelAsk token={token} channels={['sms_read', 'sms_send']}" in app
    assert "{tab === 'crm' ? <ChannelAsk token={token} channels={['telephone', 'call_recording']}" in app
    assert "{tab === 'social' ? <ChannelAsk token={token} channels={['social']}" in app


def test_the_service_worker_can_never_pin_a_browser_to_an_old_build():
    """Ctrl+R did not help, because the worker answered the navigation from its own cache."""
    worker = (PORTAL.parent / "public" / "sw-v2.js").read_text()
    # cache name is stamped per build, not a constant
    assert "concierge-studio-__BUILD__" in worker
    # a navigation is network-first with no-store, and the cached shell is for offline only
    assert "fetch(event.request, {cache: 'no-store'})" in worker
    assert "self.navigator.onLine === false" in worker
    # the old v1 worker must be gone, both the file and its registration
    assert not (PORTAL.parent / "public" / "sw.js").exists()
    app = (PORTAL / "App.tsx").read_text()
    assert "'/studio/sw-v2.js', {updateViaCache: 'none'}" in app
    assert "registration.unregister()" in app
    # and the deploy must stamp the build id
    deploy = (PORTAL.parents[2] / "scripts" / "vps" / "deploy-studio.sh").read_text()
    stamp = deploy.index("sed -i.bak")
    copy = deploy.index('echo "==> staging')
    assert stamp < copy, "the build id must be stamped before the dist is copied, or staging ships __BUILD__"
