-- Q3: Rank products by revenue within their own category, plus each product's
-- share of its category's total revenue.
-- Demonstrates: RANK() PARTITION BY, and a window aggregate (SUM() OVER) used
-- alongside a row-level value in the same query.

WITH product_revenue AS (
    SELECT
        p.product_id,
        p.product_name,
        cat.category_name,
        ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue,
        SUM(oi.quantity) AS units_sold
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id AND o.status = 'completed'
    JOIN products p ON p.product_id = oi.product_id
    JOIN categories cat ON cat.category_id = p.category_id
    GROUP BY p.product_id, p.product_name, cat.category_name
)
SELECT
    category_name,
    product_name,
    revenue,
    units_sold,
    RANK() OVER (PARTITION BY category_name ORDER BY revenue DESC) AS rank_in_category,
    ROUND(
        100.0 * revenue / SUM(revenue) OVER (PARTITION BY category_name),
        1
    ) AS pct_of_category_revenue
FROM product_revenue
ORDER BY category_name, rank_in_category;
