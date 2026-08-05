"""Data-integrity checks for the generated retail dataset.

These aren't testing application logic (there isn't any) — they're the kind
of checks a data analyst should run before trusting a dataset: referential
integrity, no orphaned rows, sane value ranges, and that each analysis query
actually executes and returns rows.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

DB_PATH = Path(__file__).resolve().parent.parent / "retail.db"
QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"


@pytest.fixture(scope="module")
def conn():
    assert DB_PATH.exists(), "retail.db not found — run generate_data.py first"
    connection = sqlite3.connect(DB_PATH)
    yield connection
    connection.close()


def scalar(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


def test_core_tables_are_populated(conn):
    for table in ["customers", "products", "categories", "orders", "order_items"]:
        count = scalar(conn, f"SELECT COUNT(*) FROM {table}")
        assert count > 0, f"{table} is empty"


def test_no_orphaned_orders(conn):
    orphans = scalar(
        conn,
        """
        SELECT COUNT(*) FROM orders o
        LEFT JOIN customers c ON c.customer_id = o.customer_id
        WHERE c.customer_id IS NULL
        """,
    )
    assert orphans == 0


def test_no_orphaned_order_items(conn):
    orphan_orders = scalar(
        conn,
        """
        SELECT COUNT(*) FROM order_items oi
        LEFT JOIN orders o ON o.order_id = oi.order_id
        WHERE o.order_id IS NULL
        """,
    )
    orphan_products = scalar(
        conn,
        """
        SELECT COUNT(*) FROM order_items oi
        LEFT JOIN products p ON p.product_id = oi.product_id
        WHERE p.product_id IS NULL
        """,
    )
    assert orphan_orders == 0
    assert orphan_products == 0


def test_no_negative_or_zero_quantities(conn):
    bad_rows = scalar(conn, "SELECT COUNT(*) FROM order_items WHERE quantity <= 0")
    assert bad_rows == 0


def test_no_negative_prices(conn):
    bad_products = scalar(conn, "SELECT COUNT(*) FROM products WHERE unit_price <= 0")
    bad_items = scalar(conn, "SELECT COUNT(*) FROM order_items WHERE unit_price <= 0")
    assert bad_products == 0
    assert bad_items == 0


def test_order_dates_within_expected_range(conn):
    min_date, max_date = conn.execute(
        "SELECT MIN(order_date), MAX(order_date) FROM orders"
    ).fetchone()
    assert min_date >= "2023-01-01"
    assert max_date <= "2025-06-30"


def test_customer_emails_are_unique(conn):
    total = scalar(conn, "SELECT COUNT(*) FROM customers")
    distinct = scalar(conn, "SELECT COUNT(DISTINCT email) FROM customers")
    assert total == distinct


@pytest.mark.parametrize(
    "filename",
    [
        "01_monthly_revenue_trend.sql",
        "02_top_customers_ltv.sql",
        "03_product_rank_within_category.sql",
        "04_signup_cohort_retention.sql",
        "05_churn_risk.sql",
    ],
)
def test_analysis_query_runs_and_returns_rows(conn, filename):
    sql = (QUERIES_DIR / filename).read_text()
    rows = conn.execute(sql).fetchall()
    assert len(rows) > 0, f"{filename} returned no rows"
