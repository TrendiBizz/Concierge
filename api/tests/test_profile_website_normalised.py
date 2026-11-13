"""A website typed by a person must survive the save, not just the read.

The setup screen reads "trendibizz.com" happily, then the save rejected the identical text with
"Enter a public HTTPS website address" and the customer could not finish setup. The reader
normalises; the validator must too.
"""
import pytest
from pydantic import ValidationError

from app.owner_onboarding import OwnerBusinessProfile


@pytest.mark.parametrize("typed, saved", [
    ("trendibizz.com", "https://trendibizz.com"),
    ("  trendibizz.com  ", "https://trendibizz.com"),
    ("http://trendibizz.com", "https://trendibizz.com"),
    ("https://trendibizz.com/contact", "https://trendibizz.com/contact"),
    ("www.trendibizz.com", "https://www.trendibizz.com"),
])
def test_a_typed_website_is_accepted_and_saved_as_https(typed, saved):
    assert OwnerBusinessProfile(site_url=typed).site_url == saved


def test_an_empty_website_stays_empty():
    assert OwnerBusinessProfile(site_url="  ").site_url == ""


@pytest.mark.parametrize("bad", [
    "https://user:secret@trendibizz.com",   # credentials in a stored reference URL
    "https://trendibizz.com/#anchor",       # fragment
    "https://nohost",                       # no dot
    "https://trendibizz.com/a b",           # whitespace
])
def test_junk_is_still_refused(bad):
    with pytest.raises(ValidationError):
        OwnerBusinessProfile(site_url=bad)
