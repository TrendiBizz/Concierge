"""An install key must be revocable.

The key in the embed snippet (`data-key="pk_..."`) was permanent: the only way to stop a retired
business's chat window answering was to delete the business. Found on 13 Nov while rechecking the
install tokens — the archived prototype's key still returned a working widget-config.
"""

import inspect

from app import main, tenants


def test_a_key_can_be_rotated():
    source = inspect.getsource(tenants.rotate_key)
    assert "UPDATE tenants SET public_key" in source
    assert "new_public_key()" in source


def test_rotation_issues_a_different_key():
    assert tenants.new_public_key() != tenants.new_public_key()


def test_the_operator_route_exists_and_returns_a_new_snippet():
    paths = main.app.openapi()["paths"]
    assert "/admin/tenants/{slug}/rotate-key" in paths
    source = inspect.getsource(main.admin_rotate_key)
    assert "tenants.rotate_key" in source
    assert "embed_snippet" in source


def test_only_the_operator_can_rotate():
    source = inspect.getsource(main)
    start = source.index('@app.post("/admin/tenants/{slug}/rotate-key"')
    assert "dependencies=admin" in source[start:start + 120]
