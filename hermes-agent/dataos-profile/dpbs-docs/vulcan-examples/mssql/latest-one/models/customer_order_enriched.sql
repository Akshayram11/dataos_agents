MODEL (
  name sales.customer_orders_enriched,
  kind full,
  start '2024-01-01',
  cron '@daily',
  grain record_id,
  description 'Enriched customer-order-product fact table with all data types and semantic-ready casting',
  tags ('enriched', 'fact', 'customer_orders', 'semantic_ready'),
  terms ('sales.analytics', 'customer.behavior', 'order.enrichment'),

  columns (
    record_id VARCHAR(10),
    customer_id VARCHAR(10),
    order_id VARCHAR(10),
    product_id VARCHAR(10),

    full_name VARCHAR(100),
    age NUMERIC(5,0),
    is_active BIT,

    signup_timestamp DATETIME,
    last_login_time DATETIME,

    order_year NUMERIC(4,0),
    order_month NUMERIC(2,0),
    order_day NUMERIC(2,0),

    total_orders NUMERIC(10,0),
    total_spent NUMERIC(12,2),
    avg_order_value NUMERIC(10,2),

    discount_percent NUMERIC(5,4),
    conversion_rate NUMERIC(5,4),

    is_returned BIT,
    return_reason VARCHAR(100),

    preferred_language VARCHAR(20),
    device_type VARCHAR(20),
    browser VARCHAR(50),

    ip_address VARCHAR(50),
    country VARCHAR(50),
    currency_code VARCHAR(10),

    loyalty_tier VARCHAR(20),
    is_subscribed BIT,

    subscription_start_date DATE,
    last_purchase_date DATE,
    days_since_last_order NUMERIC(10,0),

    credit_score NUMERIC(5,0),
    is_fraud BIT,
    risk_score NUMERIC(5,4),

    feedback_rating NUMERIC(3,1),
    feedback_comment VARCHAR(255),

    json_metadata VARCHAR(500),
    array_tags VARCHAR(255),

    geo_location VARCHAR(50),

    created_at DATE,
    updated_at DATE
  ),

  column_descriptions (
    record_id = 'Primary key for enriched record',
    customer_id = 'Reference to customer',
    order_id = 'Reference to order',
    product_id = 'Reference to product',

    total_spent = 'Total customer spend (currency formatted)',
    discount_percent = 'Discount applied (0-1, semantic percent)',
    conversion_rate = 'Conversion rate (0-1, semantic percent)',

    is_fraud = 'Fraud flag',
    risk_score = 'Risk probability score',

    json_metadata = 'Semi-structured metadata',
    array_tags = 'Pipe-separated categorical tags',

    geo_location = 'Latitude,Longitude format'
  ),

  column_tags (
    record_id = ('identifier', 'primary_key', 'grain'),

    customer_id = ('identifier', 'foreign_key'),
    order_id = ('identifier', 'foreign_key'),
    product_id = ('identifier', 'foreign_key'),

    total_spent = ('measure', 'monetary', 'currency'),
    avg_order_value = ('measure', 'monetary'),

    discount_percent = ('measure', 'percentage'),
    conversion_rate = ('measure', 'percentage'),

    total_orders = ('measure', 'count'),
    age = ('dimension', 'numeric'),

    is_active = ('dimension', 'boolean'),
    is_fraud = ('dimension', 'risk_flag'),

    signup_timestamp = ('temporal', 'timestamp'),
    last_login_time = ('temporal', 'timestamp'),

    subscription_start_date = ('temporal', 'date'),
    last_purchase_date = ('temporal', 'date'),

    geo_location = ('dimension', 'geo')
  ),

  column_terms (
    record_id = ('entity.identifier'),

    total_spent = ('revenue.metric'),
    avg_order_value = ('sales.metric'),

    discount_percent = ('pricing.discount'),
    conversion_rate = ('marketing.conversion'),

    total_orders = ('order.volume'),

    customer_id = ('customer.id'),
    order_id = ('order.id'),
    product_id = ('product.id')
  )
) ;


SELECT
  record_id,
  customer_id,
  order_id,
  product_id,

  full_name,
  CAST(age AS NUMERIC) AS age,
  CAST(is_active AS BIT) AS is_active,

  CAST(signup_timestamp AS DATETIME) AS signup_timestamp,
  CAST(last_login_time AS DATETIME) AS last_login_time,

  order_year,
  order_month,
  order_day,

  total_orders,

  -- currency
  CAST(total_spent AS NUMERIC(12,2)) AS total_spent,
  CAST(avg_order_value AS NUMERIC(10,2)) AS avg_order_value,

  -- percent (important: keep 0-1, Cube formats later)
  CAST(discount_percent AS FLOAT) AS discount_percent,
  CAST(conversion_rate AS FLOAT) AS conversion_rate,

  CAST(is_returned AS BIT) AS is_returned,
  return_reason,

  preferred_language,
  device_type,
  browser,

  ip_address,
  country,
  currency_code,

  loyalty_tier,
  CAST(is_subscribed AS BIT) AS is_subscribed,

  CAST(subscription_start_date AS DATE) AS subscription_start_date,
  CAST(last_purchase_date AS DATE) AS last_purchase_date,
  days_since_last_order,

  credit_score,
  CAST(is_fraud AS BIT) AS is_fraud,
  CAST(risk_score AS FLOAT) AS risk_score,

  feedback_rating,
  feedback_comment,

  json_metadata,
  array_tags,
  geo_location,

  CAST(created_at AS DATE) AS created_at,
  CAST(updated_at AS DATE) AS updated_at

FROM raw.customer_orders_enriched