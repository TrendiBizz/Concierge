import pytest
from fastapi import HTTPException

from app import designs


def test_safe_filename_accepts_supported():
    assert designs.safe_filename("plans v2.ifc") == "plans v2.ifc"
    assert designs.safe_filename("house.PDF") == "house.PDF"


@pytest.mark.parametrize("name", ["../etc/passwd", "x.exe", "bad<>name.pdf", ""])
def test_safe_filename_rejects(name):
    with pytest.raises(HTTPException):
        designs.safe_filename(name)
