"""The owner alert worker must be reachable through the public proxy (it only forwards /owner/*, /owner-ui, ...)."""
import pathlib

from app import main

STATIC = pathlib.Path(main.__file__).resolve().parent.parent / "static"


def _paths():
    return {getattr(route, "path", "") for route in main.app.routes}


def test_the_worker_is_served_under_a_proxied_prefix():
    paths = _paths()
    assert "/owner/sw.js" in paths
    assert "/owner-sw.js" not in paths          # that path is not forwarded by the public proxy (404 in production)


def test_the_page_registers_the_same_path_with_the_owner_scope():
    html = (STATIC / "owner.html").read_text()
    assert 'register("/owner/sw.js",{scope:"/owner-ui"})' in html
    assert "/owner-sw.js" not in html


def test_push_endpoints_exist_and_need_a_login():
    paths = _paths()
    for path in ("/owner/push/key", "/owner/push/subscribe", "/owner/push/unsubscribe", "/owner/push/test"):
        assert path in paths


def test_the_worker_file_shows_a_notification_and_opens_the_workspace():
    source = (STATIC / "owner-sw.js").read_text()
    assert "showNotification" in source and "notificationclick" in source and "/owner-ui" in source
    assert "requireInteraction" in source and "vibrate" in source
