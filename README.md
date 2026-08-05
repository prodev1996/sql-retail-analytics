# SQL Retail Analytics

A SQL-first analysis of a synthetic retail dataset — 600 customers, ~3,200 completed
orders, 20 products across 5 categories, spanning Jan 2023–Jun 2025. Built to demonstrate
real analyst SQL (CTEs, window functions, cohort analysis) rather than just `pandas.groupby`.

## What's here

- **`schema.sql`** — normalized relational schema: `customers` → `orders` → `order_items` ← `products` → `categories`.
- **`generate_data.py`** — deterministic (seeded) synthetic data generator with built-in seasonality, repeat-customer loyalty variance, and a churn tail, so the analysis has something real to say.
- **`queries/`** — five standalone `.sql` files, each answering one business question. Every query is written to be read and run independently of the notebook:
  1. `01_monthly_revenue_trend.sql` — revenue trend with month-over-month growth (`LAG()`)
  2. `02_top_customers_ltv.sql` — top customers by lifetime value (`DENSE_RANK()`)
  3. `03_product_rank_within_category.sql` — product ranking within category (`RANK() PARTITION BY`, window `SUM()`)
  4. `04_signup_cohort_retention.sql` — signup-month cohort retention analysis
  5. `05_churn_risk.sql` — customers whose order gap exceeds 2x their own historical average (`LAG()` + aggregation)
- **`analysis.ipynb`** — runs each query, visualizes the results (matplotlib/seaborn), and writes up the finding for each one. Outputs are committed, so it's readable directly on GitHub without running anything.
- **`tests/test_data_integrity.py`** — pytest suite checking referential integrity, value ranges, and that every analysis query executes and returns rows.

## Key findings (see `analysis.ipynb` for the full write-up)

- Revenue is choppy early, then compounds, with a visible Nov/Dec seasonal bump.
- The top 20 customers (of 600) account for a disproportionate share of revenue — a long-tail pattern that would justify a VIP retention play in a real business.
- Category-leading products take a noticeably larger revenue share than the rest of their category's lineup.
- Retention drops off sharply after a customer's signup month — converting first-time to second-time buyers is the highest-leverage lever here, not just acquisition.
- A gap-ratio churn rule (current gap vs. a customer's own historical average) surfaces a more personalized at-risk list than a flat days-since-last-order cutoff.

## Running it

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt

python generate_data.py             # creates retail.db
python -m pytest tests/ -v          # data integrity checks

jupyter notebook analysis.ipynb     # or: jupyter nbconvert --to notebook --execute --inplace analysis.ipynb
```

## Project structure

```text
sql-retail-analytics/
|-- schema.sql
|-- generate_data.py
|-- analysis.ipynb
|-- requirements.txt
|-- queries/
|   |-- 01_monthly_revenue_trend.sql
|   |-- 02_top_customers_ltv.sql
|   |-- 03_product_rank_within_category.sql
|   |-- 04_signup_cohort_retention.sql
|   `-- 05_churn_risk.sql
|-- scripts/
|   `-- build_notebook.py   # regenerates analysis.ipynb from its cell definitions
`-- tests/
    `-- test_data_integrity.py
```
