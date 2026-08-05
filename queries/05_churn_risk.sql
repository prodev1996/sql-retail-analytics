-- Q5: Churn risk — customers whose gap since their last order is more than
-- 2x their own historical average gap between orders (and who have at least
-- 3 orders, so the average is meaningful).
-- Demonstrates: window functions (LAG for gap calculation) combined with a
-- second aggregation pass, and a practical "flag accounts at risk" query
-- that's directly usable by a retention/marketing team.

WITH order_gaps AS (
    SELECT
        o.customer_id,
        o.order_date,
        julianday(o.order_date) - julianday(
            LAG(o.order_date) OVER (PARTITION BY o.customer_id ORDER BY o.order_date)
        ) AS days_since_prev_order
    FROM orders o
    WHERE o.status = 'completed'
),
customer_gap_stats AS (
    SELECT
        customer_id,
        COUNT(*) AS completed_orders,
        MAX(order_date) AS last_order_date,
        ROUND(AVG(days_since_prev_order), 1) AS avg_days_between_orders
    FROM order_gaps
    GROUP BY customer_id
    HAVING COUNT(*) >= 3
)
SELECT
    c.customer_id,
    cu.first_name || ' ' || cu.last_name AS customer_name,
    cu.region,
    c.completed_orders,
    c.avg_days_between_orders,
    c.last_order_date,
    CAST(julianday((SELECT MAX(order_date) FROM orders)) - julianday(c.last_order_date) AS INTEGER)
        AS days_since_last_order,
    ROUND(
        (julianday((SELECT MAX(order_date) FROM orders)) - julianday(c.last_order_date))
        / NULLIF(c.avg_days_between_orders, 0),
        2
    ) AS gap_ratio
FROM customer_gap_stats c
JOIN customers cu ON cu.customer_id = c.customer_id
WHERE
    (julianday((SELECT MAX(order_date) FROM orders)) - julianday(c.last_order_date))
    > 2 * c.avg_days_between_orders
ORDER BY gap_ratio DESC
LIMIT 25;
