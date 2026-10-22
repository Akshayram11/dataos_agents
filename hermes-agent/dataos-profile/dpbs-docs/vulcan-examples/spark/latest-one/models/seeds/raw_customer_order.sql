MODEL (
  name raw.customer_orders_enriched,
  kind SEED (
    path '../../seeds/customer_orders_enriched.csv'
  ),
  description 'Seed model loading enriched customer, order, and product level data with all data types and formats',
  tags ('seed', 'raw', 'enriched', 'customer_orders', 'semantic_testing'),
  terms ('sales.analytics', 'customer.behavior', 'order.enrichment'),

  columns (
    record_id VARCHAR(10),
    customer_id VARCHAR(10),
    order_id VARCHAR(10),
    product_id VARCHAR(10),

    full_name VARCHAR(100),
    age INT,
    is_active BOOLEAN,

    signup_timestamp VARCHAR(50),
    last_login_time VARCHAR(50),

    order_year INT,
    order_month INT,
    order_day INT,

    total_orders INT,
    total_spent DOUBLE,
    avg_order_value DOUBLE,

    discount_percent DOUBLE,
    conversion_rate DOUBLE,

    is_returned BOOLEAN,
    return_reason VARCHAR(100),

    preferred_language VARCHAR(20),
    device_type VARCHAR(20),
    browser VARCHAR(50),

    ip_address VARCHAR(50),
    country VARCHAR(50),
    currency_code VARCHAR(10),

    loyalty_tier VARCHAR(20),
    is_subscribed BOOLEAN,

    subscription_start_date DATE,
    last_purchase_date DATE,
    days_since_last_order INT,

    credit_score INT,
    is_fraud BOOLEAN,
    risk_score DOUBLE,

    feedback_rating DOUBLE,
    feedback_comment VARCHAR(255),

    json_metadata VARCHAR(500),
    array_tags VARCHAR(255),

    geo_location VARCHAR(50),

    created_at DATE,
    updated_at DATE
  ),

  grain record_id
);