# SQL Retail Analytics — Australian Supermarket Sector

A SQL-first data engineering project modeling a synthetic Australian
supermarket dataset — customers, stores, and products across Woolworths
Group and Coles Group banners in NSW, VIC, QLD, and SA — with advanced
window-function analytics for churn risk, cohort retention, and rolling
regional revenue.

## What's here

| File | Purpose |
|---|---|
| `schema.sql` | PostgreSQL DDL for `customers`, `stores`, `products`, `transactions`, with FK constraints and indexes. |
| `data_generator.py` | Seeds ~1,500 customers, 45 stores, and 10,000 transaction records using `pandas` + `Faker`. Runs against PostgreSQL or a local SQLite file. |
| `queries.sql` | Three window-function analyses: churn risk scoring, cohort retention matrix, 30-day rolling revenue/basket size. |
| `test_integrity.py` | `pytest` suite: NULL checks, positive-value checks, referential integrity, domain sanity checks. |
| `requirements.txt` | Python dependencies. |

## Data model

```text
customers ──┐
            ├──< transactions >──┐
stores ─────┘                    │
                              products
```

- **customers** — name, contact, AU state/postcode, loyalty program (`Everyday Rewards` / `Flybuys` / `None`), signup date.
- **stores** — banner (`Woolworths`, `Woolworths Metro`, `Coles`, `Coles Local`), parent group, suburb/state/postcode.
- **products** — 60+ SKUs across 13 realistic supermarket categories (Fresh Produce, Dairy & Eggs, Bakery, Liquor, etc.) with real AU brand names.
- **transactions** — one row per product purchased by a customer, at a store, on a given date (line-item grain).

## Local setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate         # macOS/Linux

pip install -r requirements.txt
```

### 2. Choose a database

**Option A — SQLite (zero config, default)**
Nothing to set up. The generator will create `retail_analytics.db` in this
folder on first run.

**Option B — PostgreSQL**

```bash
createdb retail_analytics

# Point the scripts at it, either via env var...
export DATABASE_URL="postgresql+psycopg2://<user>:<password>@localhost:5432/retail_analytics"
# ...or pass --db-url explicitly to each script (see below).
```

`data_generator.py` creates the schema itself (it runs `schema.sql` for
Postgres, or an equivalent SQLite-flavored DDL for SQLite) — you don't need
to run `schema.sql` manually, though you can if you just want to inspect or
apply the DDL on its own:

```bash
psql -d retail_analytics -f schema.sql
```

### 3. Generate the dataset

```bash
python data_generator.py
# or, customized:
python data_generator.py --db-url postgresql+psycopg2://user:pass@localhost:5432/retail_analytics \
                          --customers 2000 --stores 50 --transactions 15000 --seed 42
```

This prints row counts and total revenue on completion.

### 4. Run the analytics queries

**PostgreSQL:**

```bash
psql -d retail_analytics -f queries.sql
```

**SQLite** (note: `queries.sql` uses Postgres-specific syntax — `DATE_TRUNC`,
`generate_series`, `LATERAL` — so for a quick look at the SQLite file, open
it with a GUI tool like DB Browser for SQLite, or adapt the date functions,
or point `data_generator.py --db-url` at a real Postgres instance instead):

```bash
sqlite3 retail_analytics.db
```

### 5. Run the data quality tests

```bash
pytest test_integrity.py -v
```

By default the tests connect to the same database as the generator
(`$DATABASE_URL`, or the local SQLite file). Set `DATABASE_URL` before
running if you seeded a Postgres database instead.

## The three analyses (`queries.sql`)

1. **Customer Churn Risk Scoring** — `NTILE(4)` to isolate the top spending
   quartile, `RANK()` for lifetime-value ordering, and a days-since-last-purchase
   flag (`Low` / `High` / `Critical`) for anyone in that quartile who hasn't
   transacted in 60+ days.
2. **Cohort Retention Matrix** — groups customers by signup month, then uses
   `COUNT() OVER (PARTITION BY ...)` to size each cohort and tracks month-by-month
   retention percentage relative to month 0.
3. **30-Day Rolling Revenue & Average Basket Size per Region** — builds a full
   calendar spine per state (via `generate_series`) so gap days don't distort
   the window, then computes 7-day/30-day rolling revenue and average basket
   size with `SUM() OVER (... ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)` and
   day-over-day change via `LAG()`.

## Notes & assumptions

- The dataset is synthetic and randomly generated (seeded, so re-running
  `data_generator.py` with the same `--seed` reproduces the same data). It is
  not real Woolworths or Coles transaction data.
- The schema has no separate order/basket header table — each `transactions`
  row is one product purchase event. "Average basket size" in `queries.sql`
  is therefore approximated as the average transaction row value, noted
  inline in the query comments.
- Store locations are generated across NSW, VIC, QLD, and SA per the project
  brief; the `state` CHECK constraints allow all Australian states/territories
  for schema completeness.
