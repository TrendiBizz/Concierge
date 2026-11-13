"""The widget must not inject inline CSS: a strict CSP blocks it and the widget vanishes.

Trendi's own site has `style-src 'self'`. The widget loaded, fetched its config, and then never
appeared -- no launcher, no error a customer could see. Inline `style="..."` attributes are blocked
by style-src just like an inline `<style>` element, so the widget has to use classes and a
constructable stylesheet.
"""
import pathlib
import re

WIDGET = pathlib.Path(__file__).resolve().parents[1] / "static" / "widget.js"


def test_no_inline_style_attributes_are_injected():
    source = WIDGET.read_text()
    # `style: "..."` inside an element factory call creates a style attribute, which CSP blocks.
    offenders = re.findall(r'\bstyle\s*:\s*["\']', source)
    assert not offenders, (
        "widget.js sets an inline style attribute, which a style-src CSP blocks; "
        "use a class in the adopted stylesheet instead"
    )


def test_the_stylesheet_is_adopted_not_inlined():
    source = WIDGET.read_text()
    assert "new CSSStyleSheet()" in source and "adoptedStyleSheets" in source, (
        "the widget must adopt a constructable stylesheet, because an inline <style> is blocked"
    )


def test_runtime_style_assignments_are_still_allowed():
    """CSP permits element.style.x = ...; only inline styles in markup are blocked."""
    source = WIDGET.read_text()
    assert ".style." in source
