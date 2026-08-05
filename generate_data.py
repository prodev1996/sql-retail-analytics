"""Generate a deterministic synthetic retail dataset and load it into SQLite.

Produces a realistic multi-year order history with seasonality, repeat
customers, and a churn tail, so the analysis queries in queries/ have
something real to say.
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

SEED = 42
DB_PATH = Path(__file__).parent / "retail.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

REGIONS = ["NSW", "VIC", "QLD", "WA", "SA", "TAS"]
CATEGORIES = ["Electronics", "Home & Garden", "Apparel", "Sporting Goods", "Books"]
PRODUCTS_BY_CATEGORY = {
    "Electronics": [("Wireless Earbuds", 79.0), ("4K Monitor", 349.0), ("Bluetooth Speaker", 59.0), ("Laptop Stand", 39.0)],
    "Home & Garden": [("Ceramic Planter", 24.0), ("LED Desk Lamp", 34.0), ("Cordless Vacuum", 219.0), ("Throw Blanket", 29.0)],
    "Apparel": [("Merino Wool Jumper", 89.0), ("Running Shorts", 35.0), ("Rain Jacket", 129.0), ("Cotton Tee", 19.0)],
    "Sporting Goods": [("Yoga Mat", 45.0), ("Adjustable Dumbbells", 159.0), ("Trail Running Shoes", 149.0), ("Water Bottle", 15.0)],
    "Books": [("Data Analysis Handbook", 42.0), ("Historical Fiction Novel", 22.0), ("Cookbook: Weeknight Meals", 34.0), ("Kids Picture Book", 14.0)],
}

FIRST_NAMES = ["Olivia", "Liam", "Ava", "Noah", "Isla", "Jack", "Mia", "Lucas", "Amelia", "Ethan",
               "Chloe", "Henry", "Zoe", "Leo", "Grace", "Oscar", "Ruby", "Max", "Sophie", "Sam"]
LAST_NAMES = ["Nguyen", "Smith", "Wilson", "Chen", "Taylor", "Kumar", "Brown", "Lee", "Patel", "Walker"]


def daterange_days(start: date, end: date) -> int:
    return (end - start).days


def generate() -> None:
    rng = random.Random(SEED)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    # Categories + products
    category_ids = {}
    for i, name in enumerate(CATEGORIES, start=1):
        conn.execute("INSERT INTO categories (category_id, category_name) VALUES (?, ?)", (i, name))
        category_ids[name] = i

    product_id = 1
    products: list[tuple[int, int, float]] = []  # (product_id, category_id, unit_price)
    for cat_name, items in PRODUCTS_BY_CATEGORY.items():
        for product_name, price in items:
            conn.execute(
                "INSERT INTO products (product_id, product_name, category_id, unit_price) VALUES (?, ?, ?, ?)",
                (product_id, product_name, category_ids[cat_name], price),
            )
            products.append((product_id, category_ids[cat_name], price))
            product_id += 1

    # Customers: signups spread over 2 years, weighted so more customers joined earlier
    # (gives us a real base to compute retention/cohorts against).
    start_date = date(2023, 1, 1)
    end_date = date(2025, 6, 30)
    total_days = daterange_days(start_date, end_date)

    n_customers = 600
    customers = []
    for cid in range(1, n_customers + 1):
        signup_offset = int(rng.betavariate(1.6, 3.0) * total_days)
        signup_date = start_date + timedelta(days=signup_offset)
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}{cid}@example.com"
        region = rng.choice(REGIONS)
        customers.append((cid, first, last, email, region, signup_date))
        conn.execute(
            "INSERT INTO customers (customer_id, first_name, last_name, email, region, signup_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cid, first, last, email, region, signup_date.isoformat()),
        )

    # Orders + order_items: each customer has a random "loyalty" level that drives
    # how many orders they place after signing up, with monthly seasonality
    # (Nov/Dec uplift) and a churn tail (older customers less likely to still be active).
    order_id = 1
    order_item_id = 1
    today = end_date

    for cid, _, _, _, _, signup_date in customers:
        loyalty = rng.random()  # 0 = one-and-done, 1 = frequent repeat buyer
        days_since_signup = daterange_days(signup_date, today)
        if days_since_signup <= 0:
            continue

        expected_orders = 1 + int(loyalty * 14)
        # churn: customers who signed up long ago and are low-loyalty stop ordering early
        active_window_days = int(days_since_signup * (0.3 + 0.7 * loyalty))
        active_window_days = max(active_window_days, 1)

        n_orders = max(1, rng.binomialvariate(expected_orders, 0.7) if hasattr(rng, "binomialvariate")
                        else int(expected_orders * rng.uniform(0.5, 1.0)))

        for _ in range(n_orders):
            offset = rng.randint(0, active_window_days)
            order_date = signup_date + timedelta(days=offset)
            if order_date > today:
                continue

            # seasonality bump: nudge a slice of orders into Nov/Dec of the same year
            if rng.random() < 0.15:
                year = order_date.year
                month = rng.choice([11, 12])
                day = rng.randint(1, 28)
                candidate = date(year, month, day)
                if signup_date <= candidate <= today:
                    order_date = candidate

            status = rng.choices(["completed", "cancelled", "refunded"], weights=[0.90, 0.05, 0.05])[0]

            conn.execute(
                "INSERT INTO orders (order_id, customer_id, order_date, status) VALUES (?, ?, ?, ?)",
                (order_id, cid, order_date.isoformat(), status),
            )

            n_items = rng.randint(1, 4)
            chosen_products = rng.sample(products, k=min(n_items, len(products)))
            for pid, _cat_id, base_price in chosen_products:
                qty = rng.randint(1, 3)
                # small price jitter to simulate promos/price-at-time-of-sale
                price = round(base_price * rng.uniform(0.85, 1.05), 2)
                conn.execute(
                    "INSERT INTO order_items (order_item_id, order_id, product_id, quantity, unit_price) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (order_item_id, order_id, pid, qty, price),
                )
                order_item_id += 1

            order_id += 1

    conn.commit()

    counts = {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "order_items": conn.execute("SELECT COUNT(*) FROM order_items").fetchone()[0],
    }
    conn.close()

    print(f"Generated {DB_PATH.name}:")
    for table, n in counts.items():
        print(f"  {table}: {n:,} rows")


if __name__ == "__main__":
    generate()
