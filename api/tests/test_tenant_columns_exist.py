"""Every column we SELECT from `tenants` must exist.

The invoice page shipped 500-ing because it selected `tenants.currency_hint`, a column that was never
created. Route enumeration passed, the unit tests passed, and the only witness was a customer's
browser. This reads the SQL string literals we actually write and checks them against the schema.
"""

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
SCHEMA = APP / "schema.sql"

SQL_LITERAL = re.compile(r"""['"]([^'"]*FROM\s+tenants\b[^'"]*)['"]""", re.IGNORECASE)
SELECT_PART = re.compile(r"SELECT\s+(.*?)\s+FROM\s+tenants\b", re.IGNORECASE | re.DOTALL)


def schema_columns() -> set[str]:
    text = SCHEMA.read_text()
    start = text.index("CREATE TABLE IF NOT EXISTS tenants")
    body = text[start:text.index(");", start)]
    columns = set(re.findall(r"^\s{4}([a-z_]+)\s", body, re.MULTILINE))
    for match in re.finditer(r"ALTER TABLE tenants ADD COLUMN IF NOT EXISTS ([a-z_]+)", text):
        columns.add(match.group(1))
    return columns


def selects() -> list[tuple[str, str]]:
    """(file, column) for every plain identifier in a `SELECT ... FROM tenants` literal."""
    found = []
    for source in APP.glob("*.py"):
        text = source.read_text()
        for literal in SQL_LITERAL.finditer(text):
            clause = SELECT_PART.search(literal.group(1))
            if not clause:
                continue
            for token in clause.group(1).split(","):
                token = token.strip()
                if re.fullmatch(r"[a-z_]+", token):
                    found.append((source.name, token))
    return found


def test_the_schema_parser_found_the_columns():
    columns = schema_columns()
    assert {"id", "name", "slug", "gst_number", "quote_valid_days"} <= columns


def test_the_checker_actually_sees_our_queries():
    seen = selects()
    assert len(seen) > 20, "the checker is not matching real SQL — it would pass silently"
    assert ("invoices.py", "gst_number") in seen


def test_no_query_selects_a_tenant_column_that_does_not_exist():
    columns = schema_columns()
    unknown = sorted({(name, column) for name, column in selects() if column not in columns})
    assert not unknown, "queries select tenant columns that do not exist: " + ", ".join(
        f"{name}:{column}" for name, column in unknown)
