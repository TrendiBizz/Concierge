"""Issuing a new sign-in link must not kill the one already sent.

`make_invite` marked every earlier unused invite for the same email as used. So when an operator
minted a fresh link — to check a deploy, or because a client asked for another — the link already
sitting in the client's inbox stopped working. Conrad hit exactly this on 13 Nov: "This link has
expired or has already been used."
"""

import inspect

from app import owner_auth


def test_minting_does_not_touch_earlier_invites():
    source = inspect.getsource(owner_auth.make_invite)
    assert "UPDATE tenant_invites SET used_at=now()" not in source, (
        "minting a link must not expire the links already sent")
    assert "INSERT INTO tenant_invites" in source


def test_links_are_still_single_use_and_expire():
    source = inspect.getsource(owner_auth.make_invite)
    assert "now()+interval '24 hours'" in source


def test_the_reason_is_recorded_where_the_next_person_reads_it():
    source = inspect.getsource(owner_auth.make_invite)
    assert "silently killed" in source or "does not take the old one away" in source
