"""test_integrity.py

Automated data-quality checks for the seeded retail dataset. Run after
`python data_generator.py` with:

    pytest test_integrity.py -v

Connects to the same database as data_generator.py: $DATABASE_URL if set,
otherwise the local ./retail_analytics.db SQLite file (or pass --db-url,
see conftest-free override below via env var for simplicity).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_URL = f"sqlite:///{(PROJECT_DIR / 'retail_analytics.db').as_posix()}"
DB_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(DB_URL)
    with eng.connect() as conn:
        try:
            conn.execute(text("SELECT 1 FROM transactions LIMIT 1"))
        except Exception as exc:  # noqa: BLE001
            pytest.exit(
                f"Could not query 'transactions' table at {DB_URL!r}. "
                f"Run `python data_generator.py` first. Original error: {exc}"
            )
    yield eng
    eng.dispose()


def scalar(engine, sql: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar_one()


# ----------------------------------------------------------------------------
# Core tables are populated
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("table", ["customers", "stores", "products", "transactions"])
def test_table_is_populated(engine, table):
    count = scalar(engine, f"SELECT COUNT(*) FROM {table}")
    assert count > 0, f"{table} is empty"


def test_transaction_row_count_matches_expected_volume(engine):
    count = scalar(engine, "SELECT COUNT(*) FROM transactions")
    assert count >= 10_000, f"expected at least 10,000 transactions, found {count}"


# ----------------------------------------------------------------------------
# NULL checks on critical transaction fields
# ----------------------------------------------------------------------------

@pytest.mark.parametrize("column", ["customer_id", "store_id", "product_id", "amount", "transaction_date"])
def test_no_nulls_in_critical_transaction_fields(engine, column):
    null_count = scalar(engine, f"SELECT COUNT(*) FROM transactions WHERE {column} IS NULL")
    assert null_count == 0, f"found {null_count} NULL values in transactions.{column}"


# ----------------------------------------------------------------------------
# Positive monetary values
# ----------------------------------------------------------------------------

def test_amount_is_always_positive(engine):
    bad = scalar(engine, "SELECT COUNT(*) FROM transactions WHERE amount <= 0")
    assert bad == 0, f"found {bad} transactions with amount <= 0"


def test_unit_price_is_always_positive(engine):
    bad = scalar(engine, "SELECT COUNT(*) FROM transactions WHERE unit_price <= 0")
    assert bad == 0, f"found {bad} transactions with unit_price <= 0"


def test_quantity_is_always_positive(engine):
    bad = scalar(engine, "SELECT COUNT(*) FROM transactions WHERE quantity <= 0")
    assert bad == 0, f"found {bad} transactions with quantity <= 0"


def test_amount_never_exceeds_line_total(engine):
    # +0.01 tolerance absorbs 2dp rounding of the unrounded line total (quantity * unit_price)
    bad = scalar(engine, "SELECT COUNT(*) FROM transactions WHERE amount > ROUND(quantity * unit_price, 2) + 0.01")
    assert bad == 0, f"found {bad} transactions where amount exceeds quantity * unit_price"


# ----------------------------------------------------------------------------
# Foreign key integrity (belt-and-braces on top of DB-level constraints --
# also protects SQLite runs where FK enforcement may be off by default)
# ----------------------------------------------------------------------------

def test_all_transactions_reference_valid_customers(engine):
    orphans = scalar(engine, """
        SELECT COUNT(*) FROM transactions t
        LEFT JOIN customers c ON c.customer_id = t.customer_id
        WHERE c.customer_id IS NULL
    """)
    assert orphans == 0, f"found {orphans} transactions with no matching customer"


def test_all_transactions_reference_valid_stores(engine):
    orphans = scalar(engine, """
        SELECT COUNT(*) FROM transactions t
        LEFT JOIN stores s ON s.store_id = t.store_id
        WHERE s.store_id IS NULL
    """)
    assert orphans == 0, f"found {orphans} transactions with no matching store"


def test_all_transactions_reference_valid_products(engine):
    orphans = scalar(engine, """
        SELECT COUNT(*) FROM transactions t
        LEFT JOIN products p ON p.product_id = t.product_id
        WHERE p.product_id IS NULL
    """)
    assert orphans == 0, f"found {orphans} transactions with no matching product"


# ----------------------------------------------------------------------------
# Domain / sanity checks
# ----------------------------------------------------------------------------

def test_customer_emails_are_unique(engine):
    total = scalar(engine, "SELECT COUNT(*) FROM customers")
    distinct = scalar(engine, "SELECT COUNT(DISTINCT email) FROM customers")
    assert total == distinct, "duplicate customer emails found"


def test_states_are_valid_australian_states(engine):
    valid_states = {"NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT DISTINCT state FROM customers")).fetchall()
    found_states = {row[0] for row in rows}
    assert found_states.issubset(valid_states), f"unexpected state values: {found_states - valid_states}"


def test_no_transactions_before_customer_signup(engine):
    bad = scalar(engine, """
        SELECT COUNT(*) FROM transactions t
        JOIN customers c ON c.customer_id = t.customer_id
        WHERE t.transaction_date < c.signup_date
    """)
    assert bad == 0, f"found {bad} transactions dated before the customer's signup_date"


def test_no_future_dated_transactions(engine):
    bad = scalar(engine, "SELECT COUNT(*) FROM transactions WHERE transaction_date > CURRENT_DATE") \
        if engine.url.get_backend_name() != "sqlite" \
        else scalar(engine, "SELECT COUNT(*) FROM transactions WHERE date(transaction_date) > date('now')")
    assert bad == 0, f"found {bad} transactions dated in the future"
