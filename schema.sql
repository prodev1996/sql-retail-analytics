-- Retail analytics schema: customers, products, orders, order_items.
-- Normalized (3NF) on purpose, so the analysis queries have real joins to do.

CREATE TABLE customers (
    customer_id     INTEGER PRIMARY KEY,
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    region          TEXT NOT NULL,
    signup_date     TEXT NOT NULL  -- ISO date
);

CREATE TABLE categories (
    category_id     INTEGER PRIMARY KEY,
    category_name   TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories(category_id),
    unit_price      REAL NOT NULL
);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date      TEXT NOT NULL,  -- ISO date
    status          TEXT NOT NULL CHECK (status IN ('completed', 'cancelled', 'refunded'))
);

CREATE TABLE order_items (
    order_item_id   INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    product_id      INTEGER NOT NULL REFERENCES products(product_id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      REAL NOT NULL   -- price at time of sale, may differ from products.unit_price
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_products_category ON products(category_id);
