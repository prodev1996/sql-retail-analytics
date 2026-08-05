-- Q1: Monthly revenue trend with month-over-month growth.
-- Demonstrates: CTE, date bucketing, window function LAG() for period-over-period comparison.

WITH monthly_revenue AS (
    SELECT
        strftime('%Y-%m', o.order_date) AS month,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
        COUNT(DISTINCT o.order_id) AS orders
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.status = 'completed'
    GROUP BY month
)
SELECT
    month,
    revenue,
    orders,
    ROUND(revenue / orders, 2) AS avg_order_value,
    LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / NULLIF(LAG(revenue) OVER (ORDER BY month), 0),
        1
    ) AS mom_growth_pct
FROM monthly_revenue
ORDER BY month;
