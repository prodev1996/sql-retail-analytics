-- ============================================================================
-- queries.sql
-- Advanced window-function analytics for the Australian Retail dataset
-- (customers, stores, products, transactions -- see schema.sql).
--
-- Target: PostgreSQL 13+
-- Run any single query independently with `psql -f queries.sql` or by
-- copy-pasting one block at a time.
-- ============================================================================


-- ============================================================================
-- QUERY A: Customer Churn Risk Scoring
--
-- Identifies high-value customers (top spending quartile, via NTILE) who
-- have had no purchase activity in the last 60+ days. Ranks them by
-- lifetime spend and buckets churn severity.
-- ============================================================================
WITH customer_activity AS (
    SELECT
        c.customer_id,
        c.first_name,
        c.last_name,
        c.state,
        c.loyalty_program,
        COUNT(t.transaction_id)                  AS total_transactions,
        SUM(t.amount)                             AS lifetime_spend,
        AVG(t.amount)                              AS avg_transaction_value,
        MAX(t.transaction_date)                    AS last_transaction_date,
        (CURRENT_DATE - MAX(t.transaction_date))    AS days_since_last_purchase
    FROM customers c
    JOIN transactions t ON t.customer_id = c.customer_id
    GROUP BY c.customer_id, c.first_name, c.last_name, c.state, c.loyalty_program
),
scored AS (
    SELECT
        ca.*,
        NTILE(4) OVER (ORDER BY lifetime_spend DESC)              AS spend_quartile,
        RANK() OVER (ORDER BY lifetime_spend DESC)                AS spend_rank,
        ROUND(100.0 * lifetime_spend / SUM(lifetime_spend) OVER (), 2) AS pct_of_total_revenue
    FROM customer_activity ca
)
SELECT
    customer_id,
    first_name || ' ' || last_name       AS customer_name,
    state,
    loyalty_program,
    total_transactions,
    ROUND(lifetime_spend, 2)             AS lifetime_spend,
    ROUND(avg_transaction_value, 2)      AS avg_transaction_value,
    last_transaction_date,
    days_since_last_purchase,
    spend_rank,
    pct_of_total_revenue,
    CASE
        WHEN days_since_last_purchase >= 90 THEN 'Critical'
        WHEN days_since_last_purchase >= 60 THEN 'High'
        ELSE 'Low'
    END                                    AS churn_risk_level
FROM scored
WHERE spend_quartile = 1               -- top 25% of customers by lifetime spend
  AND days_since_last_purchase >= 60    -- inactivity threshold from the brief
ORDER BY lifetime_spend DESC, days_since_last_purchase DESC;


-- ============================================================================
-- QUERY B: Cohort Retention Matrix
--
-- Buckets customers into monthly signup cohorts and tracks what percentage
-- of each cohort is still transacting N months after signup (month 0 =
-- signup month). cohort_size is computed with COUNT() OVER (PARTITION BY ...)
-- so every customer in a cohort counts toward the denominator, even ones
-- who never transacted.
-- ============================================================================
WITH cohorts AS (
    SELECT
        customer_id,
        DATE_TRUNC('month', signup_date)::date AS cohort_month,
        COUNT(*) OVER (PARTITION BY DATE_TRUNC('month', signup_date)) AS cohort_size
    FROM customers
),
monthly_activity AS (
    SELECT DISTINCT
        customer_id,
        DATE_TRUNC('month', transaction_date)::date AS activity_month
    FROM transactions
),
cohort_activity AS (
    SELECT
        co.cohort_month,
        co.cohort_size,
        co.customer_id,
        (EXTRACT(YEAR FROM ma.activity_month) - EXTRACT(YEAR FROM co.cohort_month)) * 12
            + (EXTRACT(MONTH FROM ma.activity_month) - EXTRACT(MONTH FROM co.cohort_month)) AS month_number
    FROM cohorts co
    JOIN monthly_activity ma ON ma.customer_id = co.customer_id
    WHERE ma.activity_month >= co.cohort_month
)
SELECT
    cohort_month,
    cohort_size,
    month_number,
    COUNT(DISTINCT customer_id)                                             AS active_customers,
    ROUND(100.0 * COUNT(DISTINCT customer_id) / cohort_size, 1)             AS retention_pct
FROM cohort_activity
GROUP BY cohort_month, cohort_size, month_number
ORDER BY cohort_month, month_number;


-- ============================================================================
-- QUERY C: 30-Day Rolling Revenue & Average Basket Size per Region
--
-- Builds a complete calendar spine per state (so gap days with zero sales
-- don't silently shrink the rolling window), then computes 7-day and 30-day
-- rolling revenue plus a 30-day rolling average basket size, using window
-- frames and LAG() for day-over-day change.
--
-- NOTE: this schema has no separate order/basket header -- "basket" here is
-- approximated as a single transaction row (one product purchase event).
-- ============================================================================
WITH date_bounds AS (
    SELECT MIN(transaction_date) AS min_date, MAX(transaction_date) AS max_date
    FROM transactions
),
calendar AS (
    SELECT s.state, d::date AS transaction_date
    FROM (SELECT DISTINCT state FROM stores) s
    CROSS JOIN date_bounds db
    CROSS JOIN LATERAL generate_series(db.min_date, db.max_date, INTERVAL '1 day') AS d
),
daily_state_sales AS (
    SELECT
        cal.state,
        cal.transaction_date,
        COALESCE(SUM(t.amount), 0)     AS daily_revenue,
        COUNT(t.transaction_id)         AS daily_transactions,
        COALESCE(AVG(t.amount), 0)      AS daily_avg_basket
    FROM calendar cal
    LEFT JOIN stores s
           ON s.state = cal.state
    LEFT JOIN transactions t
           ON t.store_id = s.store_id
          AND t.transaction_date = cal.transaction_date
    GROUP BY cal.state, cal.transaction_date
),
rolling AS (
    SELECT
        state,
        transaction_date,
        daily_revenue,
        daily_transactions,
        daily_avg_basket,
        SUM(daily_revenue) OVER (
            PARTITION BY state ORDER BY transaction_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                                       AS revenue_last_7_days,
        SUM(daily_revenue) OVER (
            PARTITION BY state ORDER BY transaction_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                                       AS revenue_last_30_days,
        AVG(daily_avg_basket) OVER (
            PARTITION BY state ORDER BY transaction_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                                       AS avg_basket_last_30_days,
        LAG(daily_revenue) OVER (
            PARTITION BY state ORDER BY transaction_date
        )                                                       AS prior_day_revenue
    FROM daily_state_sales
)
SELECT
    state,
    transaction_date,
    daily_revenue,
    daily_transactions,
    ROUND(daily_avg_basket, 2)             AS daily_avg_basket,
    ROUND(revenue_last_7_days, 2)          AS revenue_last_7_days,
    ROUND(revenue_last_30_days, 2)         AS revenue_last_30_days,
    ROUND(avg_basket_last_30_days, 2)      AS avg_basket_last_30_days,
    ROUND(
        100.0 * (daily_revenue - prior_day_revenue) / NULLIF(prior_day_revenue, 0), 1
    )                                        AS day_over_day_pct_change
FROM rolling
ORDER BY state, transaction_date;
