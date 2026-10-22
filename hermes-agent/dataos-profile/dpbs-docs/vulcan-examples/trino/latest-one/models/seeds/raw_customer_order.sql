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
    age NUMBER(5,0),
    is_active BOOLEAN,

    signup_timestamp VARCHAR(50),
    last_login_time VARCHAR(50),

    order_year NUMBER(4,0),
    order_month NUMBER(2,0),
    order_day NUMBER(2,0),

    total_orders NUMBER(10,0),
    total_spent NUMBER(12,2),
    avg_order_value NUMBER(10,2),

    discount_percent NUMBER(5,4),
    conversion_rate NUMBER(5,4),

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
    days_since_last_order NUMBER(10,0),

    credit_score NUMBER(5,0),
    is_fraud BOOLEAN,
    risk_score NUMBER(5,4),

    feedback_rating NUMBER(3,1),
    feedback_comment VARCHAR(255),

    json_metadata VARCHAR(500),
    array_tags VARCHAR(255),

    geo_location VARCHAR(50),

    created_at DATE,
    updated_at DATE
  ),

  grain record_id
);