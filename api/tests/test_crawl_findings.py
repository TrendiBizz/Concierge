"""Defects found by the independent Playwright crawl of production on 2026-11-14.

Each one was observed live first, then fixed here. They are source-level guards because the
failures are in rendering and keyboard behaviour, which the API suite cannot see.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2] / "web" / "portal" / "src"


def test_the_command_palette_never_highlights_a_row_it_is_not_showing():
    """9 rows drawn, 16 commands reachable: 8 ArrowDowns landed on the last visible row, the 9th
    moved the highlight to a row that was not rendered, and Enter then navigated somewhere the
    person never saw."""
    source = (ROOT / "CmdK.tsx").read_text()
    assert "matches.slice(0, 9)" not in source, "the list is drawn with a fixed slice again"
    assert "windowStart" in source, "nothing keeps the visible window in step with the highlight"
    assert "matches.slice(windowStart" in source
    assert "setWindowStart(active" in source, "the window does not follow the highlight"
    # the highlight may reach the last match, so the window must be able to show it
    assert "Math.min(current + 1, matches.length - 1)" in source


def test_a_search_with_no_results_does_not_claim_the_business_has_no_data():
    """Both list empty states said 'No enquiries yet — that is normal on day one' and 'No contacts
    yet' while the business had rows; the search filter had simply matched nothing."""
    page = (ROOT / "CrmQuotes.tsx").read_text()
    for label in ("No enquiries match", "No contacts match"):
        assert label in page, f"missing the filtered-empty state: {label}"
    enquiries = page[page.index("No enquiries match"):]
    assert "Clear the search" in enquiries[:260]
    contacts = page[page.index("No contacts match"):]
    assert "Clear the search box" in contacts[:260]
    # the day-one copy must still exist, just only when nothing is filtered
    assert "that is normal on day one" in page and "Every enquiry creates one automatically" in page


def test_the_quotation_line_row_wraps_instead_of_clipping_the_unit_price():
    """Measured live: the row's scrollWidth was 665 inside a 358px card with overflow clipped, so
    the Unit price box sat outside the card and could not be reached or typed into."""
    page = (ROOT / "CrmQuotes.tsx").read_text()
    row = page[page.rindex("{lines.map((line, index)"):]
    row = row[:1400]
    assert "flexWrap: 'wrap'" in row, "the line row must wrap; a fixed 3-column grid clipped it"
    assert "gridTemplateColumns: '2fr 0.7fr 1fr'" not in page, "the clipping grid is back"
    assert 'aria-label="Unit price"' in row, "the unit price box disappeared entirely"


def test_a_company_can_be_opened_and_edited_not_only_deleted():
    """The only row action was Delete, so fixing a mistyped website meant deleting the company."""
    page = (ROOT / "Companies.tsx").read_text()
    assert "openEditor" in page, "there is no way to open a company"
    assert "Save the changes" in page, "the editor has no save"
    assert "/owner/companies/' + editing.id, 'PATCH'" in page, "the editor never calls the API"
    menu = page[page.index("MoreMenu label={'More actions for"):][:400]
    assert "Edit these details" in menu and "Delete this company" in menu


def test_the_setup_wizard_does_not_count_five_steps_when_it_has_three():
    shell = (ROOT / "App.tsx").read_text()
    assert "Five short steps" not in shell, "the wizard says five steps and shows three"
    assert "Three short steps" in shell
