"""An invitation link must win over whatever session the browser already holds.

Reported 2026-11-16: a Trendibizz invitation opened the Studio as ACME. The link was fine and the
token was unredeemed; the browser still held ACME's session token, and the shell only rendered the
invitation screen when it had no token at all. So the invitation was ignored, and the operator saw
the wrong business — the most convincing possible way to make a working link look broken.
"""

import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "web" / "portal" / "src"
APP = (SRC / "App.tsx").read_text(encoding="utf-8")


def shell_source() -> str:
    """Only the shell; an earlier `<Invite>` in another component must not satisfy these checks."""
    start = APP.index("function Shell()")
    return APP[start:]


def test_an_invite_in_the_url_is_rendered_even_when_a_session_exists():
    shell = shell_source()
    branch = "if (location.hash.startsWith('#invite=')) {"
    assert branch in shell, "the shell has no invite branch of its own"
    # It has to come before the signed-out/signed-in split, or a stored token wins again.
    assert shell.index(branch) < shell.index("if (!token) {"), \
        "the invite branch is after the token check, so an existing session hides it"


def test_the_old_conditional_that_only_showed_invites_when_signed_out_is_gone():
    shell = shell_source()
    assert "{location.hash.startsWith('#invite=') ? <Invite" not in shell, \
        "the invite is still nested inside the signed-out branch"


def test_a_refused_invite_offers_the_way_back_to_the_stored_account():
    assert "hasStoredSession()" in APP
    assert "Go back to the account signed in on this browser" in APP
    # It must read the same key the shell writes, or it will decide there is no session.
    assert "localStorage.getItem('concierge.token')" in APP


def test_redeeming_the_invite_replaces_the_stored_session():
    """onToken is setToken: the new tenant's token overwrites the old one. If it were a no-op
    setter, accepting Trendibizz would leave ACME signed in."""
    assert "<Invite onToken={setToken} />" in APP
    shell = shell_source()
    assert "localStorage.setItem('concierge.token', value)" in shell
