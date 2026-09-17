-- ============================================================================
-- schema.sql
-- Australian Retail Analytics -- PostgreSQL schema
--
-- Models a synthetic supermarket dataset covering customers, stores, and
-- products across Australia's two dominant grocery banners (Woolworths
-- Group and Coles Group), with a single line-item grain transactions table.
--
-- Target: PostgreSQL 13+
-- ============================================================================

DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS stores CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- ----------------------------------------------------------------------------
-- customers
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id       SERIAL PRIMARY KEY,
    first_name        VARCHAR(50)   NOT NULL,
    last_name         VARCHAR(50)   NOT NULL,
    email             VARCHAR(255)  NOT NULL UNIQUE,
    phone             VARCHAR(20),
    state             VARCHAR(3)    NOT NULL
                          CHECK (state IN ('NSW','VIC','QLD','WA','SA','TAS','ACT','NT')),
    postcode          VARCHAR(4)    NOT NULL,
    loyalty_program   VARCHAR(20)   NOT NULL DEFAULT 'None'
                          CHECK (loyalty_program IN ('Everyday Rewards','Flybuys','None')),
    signup_date       DATE          NOT NULL,
    created_at        TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- stores
-- ----------------------------------------------------------------------------
CREATE TABLE stores (
    store_id          SERIAL PRIMARY KEY,
    store_name        VARCHAR(100)  NOT NULL,
    banner            VARCHAR(30)   NOT NULL
                          CHECK (banner IN ('Woolworths','Woolworths Metro','Coles','Coles Local')),
    parent_group      VARCHAR(30)   NOT NULL
                          CHECK (parent_group IN ('Woolworths Group','Coles Group')),
    suburb            VARCHAR(100)  NOT NULL,
    state             VARCHAR(3)    NOT NULL
                          CHECK (state IN ('NSW','VIC','QLD','WA','SA','TAS','ACT','NT')),
    postcode          VARCHAR(4)    NOT NULL,
    region_type       VARCHAR(10)   NOT NULL DEFAULT 'Metro'
                          CHECK (region_type IN ('Metro','Regional')),
    opened_date       DATE,

    CONSTRAINT chk_banner_parent_group CHECK (
        (banner IN ('Woolworths','Woolworths Metro') AND parent_group = 'Woolworths Group')
        OR
        (banner IN ('Coles','Coles Local') AND parent_group = 'Coles Group')
    )
);

-- ----------------------------------------------------------------------------
-- products
-- ----------------------------------------------------------------------------
CREATE TABLE products (
    product_id        SERIAL PRIMARY KEY,
    product_name      VARCHAR(150)  NOT NULL,
    category          VARCHAR(40)   NOT NULL
                          CHECK (category IN (
                              'Fresh Produce','Meat & Seafood','Dairy & Eggs','Bakery',
                              'Pantry & Dry Goods','Frozen Foods','Beverages',
                              'Snacks & Confectionery','Household & Cleaning',
                              'Health & Beauty','Baby Care','Pet Care','Liquor'
                          )),
    brand             VARCHAR(60)   NOT NULL,
    unit_of_measure   VARCHAR(10)   NOT NULL DEFAULT 'each'
                          CHECK (unit_of_measure IN ('each','kg','g','L','mL','pack')),
    unit_price        NUMERIC(8,2)  NOT NULL CHECK (unit_price > 0)
);

-- ----------------------------------------------------------------------------
-- transactions
-- One row per product purchased by a customer, at a store, on a given date.
-- (Line-item grain -- there is no separate "basket"/order header table.)
-- ----------------------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id    BIGSERIAL PRIMARY KEY,
    customer_id       INTEGER       NOT NULL REFERENCES customers(customer_id),
    store_id          INTEGER       NOT NULL REFERENCES stores(store_id),
    product_id        INTEGER       NOT NULL REFERENCES products(product_id),
    transaction_date  DATE          NOT NULL,
    quantity          INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price        NUMERIC(8,2)  NOT NULL CHECK (unit_price > 0),
    discount_amount   NUMERIC(8,2)  NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    amount            NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    payment_method    VARCHAR(20)   NOT NULL
                          CHECK (payment_method IN (
                              'EFTPOS','Debit Card','Credit Card','Apple Pay','Google Pay','Gift Card','Cash'
                          )),

    -- +0.01 tolerance absorbs 2dp rounding of the unrounded line total (quantity * unit_price)
    CONSTRAINT chk_amount_within_line_total CHECK (amount <= ROUND(quantity * unit_price, 2) + 0.01)
);

-- ----------------------------------------------------------------------------
-- Indexing
-- ----------------------------------------------------------------------------
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
