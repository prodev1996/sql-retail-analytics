#!/usr/bin/env python
"""data_generator.py

Seeds a synthetic Australian supermarket dataset (customers, stores,
products, transactions) into either PostgreSQL or a local SQLite file,
modeled on the two dominant AU grocery banners: Woolworths Group and
Coles Group.

Usage
-----
    # Zero-config: writes to ./retail_analytics.db (SQLite)
    python data_generator.py

    # Custom volumes
    python data_generator.py --customers 2000 --stores 45 --transactions 10000

    # Postgres (either flag or DATABASE_URL env var)
    python data_generator.py --db-url postgresql+psycopg2://user:pass@localhost:5432/retail_analytics
    DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/retail_analytics python data_generator.py

Requires: pandas, Faker, SQLAlchemy, psycopg2-binary (only for Postgres).
"""
from __future__ import annotations

import argparse
import os
import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker
from sqlalchemy import create_engine, text

PROJECT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = PROJECT_DIR / "schema.sql"
DEFAULT_SQLITE_URL = f"sqlite:///{(PROJECT_DIR / 'retail_analytics.db').as_posix()}"

# ----------------------------------------------------------------------------
# Reference data
# ----------------------------------------------------------------------------

# Spec calls out SA, NSW, VIC, QLD specifically -- weighted roughly by
# real-world population share, heaviest on the eastern seaboard.
STATE_WEIGHTS: dict[str, float] = {
    "NSW": 0.35,
    "VIC": 0.30,
    "QLD": 0.20,
    "SA": 0.15,
}

# Real AU postcode ranges per state, used to generate plausible postcodes.
STATE_POSTCODE_RANGES: dict[str, list[tuple[int, int]]] = {
    "NSW": [(2000, 2599), (2619, 2899), (2921, 2999)],
    "VIC": [(3000, 3999)],
    "QLD": [(4000, 4999)],
    "SA": [(5000, 5799)],
}

STATE_SUBURBS: dict[str, list[str]] = {
    "NSW": ["Sydney CBD", "Parramatta", "Chatswood", "Bondi Junction", "Newcastle",
            "Wollongong", "Penrith", "Liverpool", "Hurstville", "Blacktown"],
    "VIC": ["Melbourne CBD", "Southbank", "Richmond", "Box Hill", "Geelong",
            "Ballarat", "Dandenong", "Frankston", "Footscray", "Werribee"],
    "QLD": ["Brisbane CBD", "Fortitude Valley", "Chermside", "Toowoomba", "Cairns",
            "Townsville", "Surfers Paradise", "Maroochydore", "Ipswich", "Logan Central"],
    "SA": ["Adelaide CBD", "Glenelg", "Norwood", "Marion", "Elizabeth",
           "Mount Barker", "Port Adelaide", "Modbury", "Salisbury", "Mawson Lakes"],
}

LOYALTY_BY_GROUP = {
    "Woolworths Group": "Everyday Rewards",
    "Coles Group": "Flybuys",
}

PAYMENT_METHODS = ["EFTPOS", "Debit Card", "Credit Card", "Apple Pay", "Google Pay", "Cash", "Gift Card"]
PAYMENT_WEIGHTS = [0.35, 0.25, 0.20, 0.10, 0.05, 0.03, 0.02]

# (product_name, category, brand, unit_of_measure, base_price)
PRODUCT_CATALOG: list[tuple[str, str, str, str, float]] = [
    # Fresh Produce
    ("Cavendish Bananas", "Fresh Produce", "Woolworths", "kg", 3.90),
    ("Pink Lady Apples", "Fresh Produce", "Coles", "kg", 4.50),
    ("Hass Avocado", "Fresh Produce", "Perfection Fresh", "each", 2.20),
    ("Roma Tomatoes", "Fresh Produce", "Woolworths", "kg", 5.90),
    ("Brown Onions", "Fresh Produce", "Coles", "kg", 2.80),
    ("Baby Spinach 120g", "Fresh Produce", "Woolworths", "each", 3.50),
    ("Carrots 1kg", "Fresh Produce", "Coles", "each", 2.10),
    # Meat & Seafood
    ("Beef Mince 500g", "Meat & Seafood", "Woolworths", "each", 7.50),
    ("Chicken Breast Fillets", "Meat & Seafood", "Coles", "kg", 11.00),
    ("Lamb Chops", "Meat & Seafood", "Woolworths", "kg", 16.50),
    ("Atlantic Salmon Fillet", "Meat & Seafood", "Coles Finest", "kg", 32.00),
    ("Pork Sausages 500g", "Meat & Seafood", "Primo", "each", 6.80),
    # Dairy & Eggs
    ("Full Cream Milk 2L", "Dairy & Eggs", "Dairy Farmers", "each", 3.60),
    ("Free Range Eggs 12pk", "Dairy & Eggs", "Woolworths", "each", 6.50),
    ("Tasty Cheese Block 500g", "Dairy & Eggs", "Coles", "each", 7.00),
    ("Butter 500g", "Dairy & Eggs", "Western Star", "each", 6.20),
    ("Greek Yoghurt 1kg", "Dairy & Eggs", "Chobani", "each", 6.90),
    # Bakery
    ("White Sandwich Loaf", "Bakery", "Tip Top", "each", 4.20),
    ("Multigrain Loaf", "Bakery", "Helga's", "each", 5.10),
    ("Dinner Rolls 6pk", "Bakery", "Woolworths", "each", 3.80),
    ("Chocolate Muffins 4pk", "Bakery", "Coles Bakery", "each", 5.50),
    # Pantry & Dry Goods
    ("Pasta Spaghetti 500g", "Pantry & Dry Goods", "San Remo", "each", 2.20),
    ("Basmati Rice 1kg", "Pantry & Dry Goods", "SunRice", "each", 4.50),
    ("Vegemite 220g", "Pantry & Dry Goods", "Vegemite", "each", 5.80),
    ("Rolled Oats 1kg", "Pantry & Dry Goods", "Uncle Tobys", "each", 4.90),
    ("Extra Virgin Olive Oil 750mL", "Pantry & Dry Goods", "Cobram Estate", "each", 12.00),
    ("Peanut Butter 500g", "Pantry & Dry Goods", "Bega", "each", 5.40),
    # Frozen Foods
    ("Frozen Mixed Vegetables 1kg", "Frozen Foods", "Birds Eye", "each", 4.60),
    ("Frozen Margherita Pizza", "Frozen Foods", "Dr. Oetker", "each", 6.50),
    ("Vanilla Ice Cream 2L", "Frozen Foods", "Streets", "each", 8.00),
    ("Frozen Chips 1kg", "Frozen Foods", "McCain", "each", 4.20),
    # Beverages
    ("Coca-Cola 1.25L", "Beverages", "Coca-Cola", "each", 3.30),
    ("Orange Juice 2L", "Beverages", "Berri", "each", 5.90),
    ("Ground Coffee 200g", "Beverages", "Vittoria", "each", 9.50),
    ("Spring Water 24pk", "Beverages", "Mount Franklin", "each", 12.00),
    ("Milo 1kg", "Beverages", "Nestle", "each", 13.50),
    # Snacks & Confectionery
    ("Tim Tam Original 200g", "Snacks & Confectionery", "Arnott's", "each", 4.20),
    ("Potato Chips 175g", "Snacks & Confectionery", "Smith's", "each", 4.50),
    ("Dairy Milk Chocolate 180g", "Snacks & Confectionery", "Cadbury", "each", 5.00),
    ("Shapes Crackers 175g", "Snacks & Confectionery", "Arnott's", "each", 3.90),
    # Household & Cleaning
    ("Laundry Powder 2kg", "Household & Cleaning", "Omo", "each", 14.00),
    ("Dishwashing Liquid 400mL", "Household & Cleaning", "Morning Fresh", "each", 3.60),
    ("Toilet Paper 12pk", "Household & Cleaning", "Quilton", "each", 8.50),
    ("Paper Towel 4pk", "Household & Cleaning", "Kleenex", "each", 7.20),
    ("Multi-Surface Spray 750mL", "Household & Cleaning", "Glen 20", "each", 6.00),
    # Health & Beauty
    ("Shampoo 400mL", "Health & Beauty", "Pantene", "each", 8.00),
    ("Toothpaste 110g", "Health & Beauty", "Colgate", "each", 4.50),
    ("Body Wash 500mL", "Health & Beauty", "Dove", "each", 7.50),
    ("Sunscreen SPF50 200mL", "Health & Beauty", "Cancer Council", "each", 15.00),
    # Baby Care
    ("Baby Nappies Size 3 40pk", "Baby Care", "Huggies", "each", 18.00),
    ("Baby Wipes 80pk", "Baby Care", "Johnson's", "each", 5.50),
    ("Infant Formula 900g", "Baby Care", "Aptamil", "each", 32.00),
    # Pet Care
    ("Dry Dog Food 3kg", "Pet Care", "Pedigree", "each", 16.00),
    ("Cat Food Pouches 12pk", "Pet Care", "Whiskas", "each", 11.50),
    ("Cat Litter 8kg", "Pet Care", "Catsan", "each", 14.50),
    # Liquor
    ("Lager Beer 24pk Cans", "Liquor", "Carlton Draught", "each", 52.00),
    ("Shiraz Red Wine 750mL", "Liquor", "Jacob's Creek", "each", 14.00),
    ("Sauvignon Blanc 750mL", "Liquor", "Oyster Bay", "each", 18.00),
]

# High-frequency categories get sampled more often than low-frequency ones,
# which is realistic for a weekly supermarket shop.
CATEGORY_FREQUENCY_WEIGHTS = {
    "Fresh Produce": 1.6,
    "Dairy & Eggs": 1.5,
    "Bakery": 1.3,
    "Pantry & Dry Goods": 1.3,
    "Beverages": 1.2,
    "Snacks & Confectionery": 1.2,
    "Meat & Seafood": 1.1,
    "Frozen Foods": 1.0,
    "Household & Cleaning": 0.9,
    "Health & Beauty": 0.7,
    "Liquor": 0.6,
    "Pet Care": 0.5,
    "Baby Care": 0.4,
}

TRANSACTION_WINDOW_DAYS = 730  # ~2 years of trading history


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def pick_state(rng: random.Random) -> str:
    states = list(STATE_WEIGHTS.keys())
    weights = list(STATE_WEIGHTS.values())
    return rng.choices(states, weights=weights, k=1)[0]


def pick_postcode(rng: random.Random, state: str) -> str:
    lo, hi = rng.choice(STATE_POSTCODE_RANGES[state])
    return f"{rng.randint(lo, hi):04d}"


def pick_banner(rng: random.Random) -> tuple[str, str]:
    parent_group = rng.choice(["Woolworths Group", "Coles Group"])
    if parent_group == "Woolworths Group":
        banner = rng.choices(["Woolworths", "Woolworths Metro"], weights=[0.85, 0.15], k=1)[0]
    else:
        banner = rng.choices(["Coles", "Coles Local"], weights=[0.85, 0.15], k=1)[0]
    return banner, parent_group


# ----------------------------------------------------------------------------
# Generators
# ----------------------------------------------------------------------------

def generate_stores(n_stores: int, rng: random.Random) -> pd.DataFrame:
    rows = []
    for store_id in range(1, n_stores + 1):
        state = pick_state(rng)
        suburb = rng.choice(STATE_SUBURBS[state])
        banner, parent_group = pick_banner(rng)
        region_type = "Metro" if "CBD" in suburb or rng.random() < 0.75 else "Regional"
        opened_date = date(2000, 1, 1) + timedelta(days=rng.randint(0, 9000))

        rows.append({
            "store_id": store_id,
            "store_name": f"{banner} {suburb}",
            "banner": banner,
            "parent_group": parent_group,
            "suburb": suburb,
            "state": state,
            "postcode": pick_postcode(rng, state),
            "region_type": region_type,
            "opened_date": opened_date.isoformat(),
        })
    return pd.DataFrame(rows)


def generate_customers(n_customers: int, rng: random.Random, faker: Faker) -> pd.DataFrame:
    today = date.today()
    signup_start = today - timedelta(days=TRANSACTION_WINDOW_DAYS + 180)

    rows = []
    for customer_id in range(1, n_customers + 1):
        state = pick_state(rng)
        first_name = faker.first_name()
        last_name = faker.last_name()
        email = f"{first_name.lower()}.{last_name.lower()}{customer_id}@example.com.au"
        phone = f"04{rng.randint(0, 99):02d} {rng.randint(0, 999):03d} {rng.randint(0, 999):03d}"

        # Skew signups earlier so cohorts have enough history to show retention decay.
        signup_offset_days = int(rng.betavariate(1.6, 3.0) * (today - signup_start).days)
        signup_date = signup_start + timedelta(days=signup_offset_days)

        _, parent_group = pick_banner(rng)
        loyalty_program = LOYALTY_BY_GROUP[parent_group] if rng.random() < 0.8 else "None"

        rows.append({
            "customer_id": customer_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "state": state,
            "postcode": pick_postcode(rng, state),
            "loyalty_program": loyalty_program,
            "signup_date": signup_date.isoformat(),
        })
    return pd.DataFrame(rows)


def generate_products() -> pd.DataFrame:
    rows = [
        {
            "product_id": i,
            "product_name": name,
            "category": category,
            "brand": brand,
            "unit_of_measure": uom,
            "unit_price": price,
        }
        for i, (name, category, brand, uom, price) in enumerate(PRODUCT_CATALOG, start=1)
    ]
    return pd.DataFrame(rows)


def generate_transactions(
    n_transactions: int,
    customers: pd.DataFrame,
    stores: pd.DataFrame,
    products: pd.DataFrame,
    rng: random.Random,
    np_rng: np.random.Generator,
) -> pd.DataFrame:
    today = date.today()

    # Long-tail customer activity: a handful of loyal shoppers transact often,
    # most transact occasionally, some barely at all (churn candidates).
    activity_weights = np_rng.exponential(scale=1.0, size=len(customers)) + 0.05
    activity_weights /= activity_weights.sum()

    customer_ids = customers["customer_id"].to_numpy()
    customer_state = customers.set_index("customer_id")["state"].to_dict()
    customer_signup = customers.set_index("customer_id")["signup_date"].to_dict()

    stores_by_state: dict[str, list[int]] = {}
    for state, group in stores.groupby("state"):
        stores_by_state[state] = group["store_id"].tolist()
    all_store_ids = stores["store_id"].tolist()

    categories = products["category"].unique().tolist()
    category_weights = [CATEGORY_FREQUENCY_WEIGHTS.get(c, 1.0) for c in categories]
    products_by_category: dict[str, list[int]] = {
        cat: group["product_id"].tolist() for cat, group in products.groupby("category")
    }
    product_price = products.set_index("product_id")["unit_price"].to_dict()

    chosen_customer_ids = np_rng.choice(customer_ids, size=n_transactions, p=activity_weights)

    rows = []
    for i in range(n_transactions):
        customer_id = int(chosen_customer_ids[i])
        state = customer_state[customer_id]
        signup_date = date.fromisoformat(customer_signup[customer_id])

        # 90% of purchases happen at a store in the customer's own state.
        if rng.random() < 0.90 and state in stores_by_state:
            store_id = rng.choice(stores_by_state[state])
        else:
            store_id = rng.choice(all_store_ids)

        window_days = max((today - signup_date).days, 1)
        transaction_date = signup_date + timedelta(days=rng.randint(0, window_days))

        category = rng.choices(categories, weights=category_weights, k=1)[0]
        product_id = rng.choice(products_by_category[category])
        base_price = product_price[product_id]

        quantity = rng.choices([1, 2, 3, 4], weights=[0.5, 0.3, 0.15, 0.05], k=1)[0]
        unit_price = round(base_price * rng.uniform(0.95, 1.05), 2)

        line_total = round(quantity * unit_price, 2)
        discount_pct = rng.choices([0, 0.10, 0.15, 0.20, 0.30], weights=[0.80, 0.08, 0.06, 0.04, 0.02], k=1)[0]
        discount_amount = round(line_total * discount_pct, 2)
        amount = round(line_total - discount_amount, 2)

        payment_method = rng.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS, k=1)[0]

        rows.append({
            "transaction_id": i + 1,
            "customer_id": customer_id,
            "store_id": int(store_id),
            "product_id": product_id,
            "transaction_date": transaction_date.isoformat(),
            "quantity": quantity,
            "unit_price": unit_price,
            "discount_amount": discount_amount,
            "amount": amount,
            "payment_method": payment_method,
        })

    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Schema / load
# ----------------------------------------------------------------------------

SQLITE_SCHEMA = """
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS stores;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
    customer_id      INTEGER PRIMARY KEY,
    first_name       TEXT NOT NULL,
    last_name        TEXT NOT NULL,
    email            TEXT NOT NULL UNIQUE,
    phone            TEXT,
    state            TEXT NOT NULL CHECK (state IN ('NSW','VIC','QLD','WA','SA','TAS','ACT','NT')),
    postcode         TEXT NOT NULL,
    loyalty_program  TEXT NOT NULL DEFAULT 'None' CHECK (loyalty_program IN ('Everyday Rewards','Flybuys','None')),
    signup_date      TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE stores (
    store_id         INTEGER PRIMARY KEY,
    store_name       TEXT NOT NULL,
    banner           TEXT NOT NULL CHECK (banner IN ('Woolworths','Woolworths Metro','Coles','Coles Local')),
    parent_group     TEXT NOT NULL CHECK (parent_group IN ('Woolworths Group','Coles Group')),
    suburb           TEXT NOT NULL,
    state            TEXT NOT NULL CHECK (state IN ('NSW','VIC','QLD','WA','SA','TAS','ACT','NT')),
    postcode         TEXT NOT NULL,
    region_type      TEXT NOT NULL DEFAULT 'Metro' CHECK (region_type IN ('Metro','Regional')),
    opened_date      TEXT,
    CHECK (
        (banner IN ('Woolworths','Woolworths Metro') AND parent_group = 'Woolworths Group')
        OR
        (banner IN ('Coles','Coles Local') AND parent_group = 'Coles Group')
    )
);

CREATE TABLE products (
    product_id       INTEGER PRIMARY KEY,
    product_name     TEXT NOT NULL,
    category         TEXT NOT NULL CHECK (category IN (
                         'Fresh Produce','Meat & Seafood','Dairy & Eggs','Bakery',
                         'Pantry & Dry Goods','Frozen Foods','Beverages',
                         'Snacks & Confectionery','Household & Cleaning',
                         'Health & Beauty','Baby Care','Pet Care','Liquor'
                     )),
    brand            TEXT NOT NULL,
    unit_of_measure  TEXT NOT NULL DEFAULT 'each' CHECK (unit_of_measure IN ('each','kg','g','L','mL','pack')),
    unit_price       REAL NOT NULL CHECK (unit_price > 0)
);

CREATE TABLE transactions (
    transaction_id    INTEGER PRIMARY KEY,
    customer_id       INTEGER NOT NULL REFERENCES customers(customer_id),
    store_id          INTEGER NOT NULL REFERENCES stores(store_id),
    product_id        INTEGER NOT NULL REFERENCES products(product_id),
    transaction_date  TEXT NOT NULL,
    quantity          INTEGER NOT NULL CHECK (quantity > 0),
    unit_price        REAL NOT NULL CHECK (unit_price > 0),
    discount_amount   REAL NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    amount            REAL NOT NULL CHECK (amount > 0),
    payment_method    TEXT NOT NULL CHECK (payment_method IN (
                          'EFTPOS','Debit Card','Credit Card','Apple Pay','Google Pay','Gift Card','Cash'
                      )),
    CHECK (amount <= ROUND(quantity * unit_price, 2) + 0.01)
);

CREATE INDEX idx_customers_state            ON customers(state);
CREATE INDEX idx_customers_signup_date      ON customers(signup_date);
CREATE INDEX idx_stores_state               ON stores(state);
CREATE INDEX idx_stores_parent_group        ON stores(parent_group);
CREATE INDEX idx_products_category          ON products(category);
CREATE INDEX idx_transactions_customer_id   ON transactions(customer_id);
CREATE INDEX idx_transactions_store_id      ON transactions(store_id);
CREATE INDEX idx_transactions_product_id    ON transactions(product_id);
CREATE INDEX idx_transactions_date          ON transactions(transaction_date);
CREATE INDEX idx_transactions_customer_date ON transactions(customer_id, transaction_date);
"""


def create_schema(engine) -> None:
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    ddl = SQLITE_SCHEMA if is_sqlite else SCHEMA_PATH.read_text(encoding="utf-8")

    with engine.begin() as conn:
        if is_sqlite:
            conn.exec_driver_sql("PRAGMA foreign_keys = OFF")  # dropping tables in FK order below
        for statement in ddl.split(";"):
            statement = statement.strip()
            if statement:
                conn.exec_driver_sql(statement)


def reset_postgres_sequences(engine) -> None:
    if engine.url.get_backend_name() != "postgresql":
        return
    with engine.begin() as conn:
        for table, id_col in [
            ("customers", "customer_id"),
            ("stores", "store_id"),
            ("products", "product_id"),
            ("transactions", "transaction_id"),
        ]:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{id_col}'), "
                f"COALESCE((SELECT MAX({id_col}) FROM {table}), 1))"
            ))


def load(engine, customers: pd.DataFrame, stores: pd.DataFrame,
         products: pd.DataFrame, transactions: pd.DataFrame) -> None:
    customers.to_sql("customers", engine, if_exists="append", index=False)
    stores.to_sql("stores", engine, if_exists="append", index=False)
    products.to_sql("products", engine, if_exists="append", index=False)
    transactions.to_sql("transactions", engine, if_exists="append", index=False)
    reset_postgres_sequences(engine)


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL),
                         help="SQLAlchemy connection string. Defaults to a local SQLite file, "
                              "or $DATABASE_URL if set.")
    parser.add_argument("--customers", type=int, default=1500, help="Number of customers to generate.")
    parser.add_argument("--stores", type=int, default=45, help="Number of stores to generate.")
    parser.add_argument("--transactions", type=int, default=10000, help="Number of transaction rows to generate.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rng = random.Random(args.seed)
    np_rng = np.random.default_rng(args.seed)
    faker = Faker("en_AU")
    Faker.seed(args.seed)

    engine = create_engine(args.db_url)

    print(f"Target database : {engine.url.render_as_string(hide_password=True)}")
    print("Creating schema...")
    create_schema(engine)

    print(f"Generating {args.stores:,} stores...")
    stores = generate_stores(args.stores, rng)

    print(f"Generating {args.customers:,} customers...")
    customers = generate_customers(args.customers, rng, faker)

    print(f"Generating {len(PRODUCT_CATALOG):,} products...")
    products = generate_products()

    print(f"Generating {args.transactions:,} transactions...")
    transactions = generate_transactions(args.transactions, customers, stores, products, rng, np_rng)

    print("Loading into database...")
    load(engine, customers, stores, products, transactions)

    print("\nDone. Row counts:")
    print(f"  customers    : {len(customers):,}")
    print(f"  stores       : {len(stores):,}")
    print(f"  products     : {len(products):,}")
    print(f"  transactions : {len(transactions):,}")
    print(f"  total revenue: ${transactions['amount'].sum():,.2f}")


if __name__ == "__main__":
    main()
