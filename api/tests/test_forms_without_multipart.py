"""Form posts must work in the image we actually ship.

`request.form()` asserts `python-multipart` is installed, even for urlencoded bodies. It is not in the
image, so every form post raised: the public privacy form 500-ed, and the quote's "pay deposit" choice
silently fell back to full price.
"""

import asyncio
from types import SimpleNamespace

from app.forms import read_form


class FakeRequest:
    def __init__(self, body: bytes, content_type: str = "application/x-www-form-urlencoded"):
        self._body = body
        self.headers = {"content-type": content_type}

    async def body(self):
        return self._body

    async def form(self):
        raise AssertionError("The `python-multipart` library must be installed to use form parsing.")


def read(body: bytes, content_type: str = "application/x-www-form-urlencoded"):
    return asyncio.run(read_form(FakeRequest(body, content_type)))


def test_urlencoded_fields_are_read_without_multipart():
    assert read(b"payment_option=deposit&email=a%40b.co") == {
        "payment_option": "deposit", "email": "a@b.co"}


def test_blank_values_and_empty_bodies_are_safe():
    assert read(b"") == {}
    assert read(b"note=&kind=delete") == {"note": "", "kind": "delete"}


def test_a_multipart_post_without_the_parser_does_not_500():
    assert read(b"--x\r\n", "multipart/form-data; boundary=x") == {}


def test_plus_and_repeat_keys_are_handled_like_a_browser():
    assert read(b"note=hello+world&note=second")["note"] == "hello world"
