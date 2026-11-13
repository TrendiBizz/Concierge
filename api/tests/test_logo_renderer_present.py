"""A missing renderer must be loud, not silent.

In production the API image was built from a stale requirements lock that omitted `resvg_py`.
Every logo then failed to draw, the owner was told their website's logo could not be turned into
an image, and nothing was logged. Blaming a customer's site for our own missing dependency is
the worst kind of failure: plausible, quiet and wrong.
"""
import builtins

from app import brand_from_site


def test_a_missing_renderer_is_reported_not_hidden(monkeypatch, caplog):
    real_import = builtins.__import__

    def no_resvg(name, *args, **kwargs):
        if name == "resvg_py":
            raise ImportError("resvg_py is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_resvg)
    monkeypatch.setattr(brand_from_site, "_RENDERER_MISSING_LOGGED", False)

    with caplog.at_level("ERROR", logger="concierge.brand"):
        assert brand_from_site.rasterise_svg("<svg xmlns='http://www.w3.org/2000/svg'/>") is None

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "resvg_py" in messages or "renderer unavailable" in messages, \
        "an image without a renderer must say so in the log"


def test_it_complains_only_once_so_a_page_of_logos_is_not_a_flood(monkeypatch, caplog):
    real_import = builtins.__import__

    def no_resvg(name, *args, **kwargs):
        if name == "resvg_py":
            raise ImportError("resvg_py is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_resvg)
    monkeypatch.setattr(brand_from_site, "_RENDERER_MISSING_LOGGED", False)
    with caplog.at_level("ERROR", logger="concierge.brand"):
        for _ in range(5):
            brand_from_site.rasterise_svg("<svg/>")
    assert len([r for r in caplog.records if "renderer unavailable" in r.getMessage()]) == 1
