-- Q4: Signup-month cohort retention — of customers who signed up in month M,
-- what share placed a completed order in each of the following 3 months?
-- Demonstrates: cohort analysis pattern with CTEs, LEFT JOIN + CASE aggregation,
-- and date-diff bucketing (a common real-world SQL analyst task).

WITH cohorts AS (
    SELECT
        customer_id,
        strftime('%Y-%m', signup_date) AS cohort_month
    FROM customers
),
customer_orders AS (
    SELECT
        o.customer_id,
        strftime('%Y-%m', o.order_date) AS order_month
    FROM orders o
    WHERE o.status = 'completed'
    GROUP BY o.customer_id, order_month
),
cohort_activity AS (
    SELECT
        c.cohort_month,
        c.customer_id,
        (CAST(strftime('%Y', co.order_month || '-01') AS INTEGER) * 12
            + CAST(strftime('%m', co.order_month || '-01') AS INTEGER))
        -
        (CAST(strftime('%Y', c.cohort_month || '-01') AS INTEGER) * 12
            + CAST(strftime('%m', c.cohort_month || '-01') AS INTEGER)) AS months_since_signup
    FROM cohorts c
    JOIN customer_orders co ON co.customer_id = c.customer_id
)
SELECT
    cohort_month,
    COUNT(DISTINCT customer_id) FILTER (WHERE months_since_signup = 0) AS month_0_active,
    COUNT(DISTINCT customer_id) FILTER (WHERE months_since_signup = 1) AS month_1_active,
    COUNT(DISTINCT customer_id) FILTER (WHERE months_since_signup = 2) AS month_2_active,
    COUNT(DISTINCT customer_id) FILTER (WHERE months_since_signup = 3) AS month_3_active
FROM cohort_activity
GROUP BY cohort_month
ORDER BY cohort_month;
