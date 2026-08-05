-- Q2: Top 20 customers by lifetime value (a lightweight RFM view).
-- Demonstrates: multi-table joins, aggregation, DENSE_RANK() window function.

WITH customer_orders AS (
    SELECT
        c.customer_id,
        c.first_name || ' ' || c.last_name AS customer_name,
        c.region,
        COUNT(DISTINCT o.order_id) AS total_orders,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS lifetime_value,
        MIN(o.order_date) AS first_order_date,
        MAX(o.order_date) AS last_order_date
    FROM customers c
    JOIN orders o ON o.customer_id = c.customer_id AND o.status = 'completed'
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY c.customer_id, customer_name, c.region
)
SELECT
    customer_id,
    customer_name,
    region,
    total_orders,
    lifetime_value,
    ROUND(lifetime_value / total_orders, 2) AS avg_order_value,
    first_order_date,
    last_order_date,
    DENSE_RANK() OVER (ORDER BY lifetime_value DESC) AS ltv_rank
FROM customer_orders
ORDER BY lifetime_value DESC
LIMIT 20;
