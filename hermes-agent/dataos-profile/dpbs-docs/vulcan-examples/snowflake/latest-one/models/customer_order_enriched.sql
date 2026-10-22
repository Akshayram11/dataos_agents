MODEL (
  name lenovo.sales.customer_orders_enriched,
  kind full,
  start '2024-01-01',
  cron '@daily',
  grain RECORD_ID,
  description 'Enriched customer-order-product fact table with all data types and semantic-ready casting',
  tags ('enriched', 'fact', 'customer_orders', 'semantic_ready'),
  terms ('sales.analytics', 'customer.behavior', 'order.enrichment'),

  columns (
    RECORD_ID VARCHAR(10),
    CUSTOMER_ID VARCHAR(10),
    ORDER_ID VARCHAR(10),
    PRODUCT_ID VARCHAR(10),

    FULL_NAME VARCHAR(100),
    AGE NUMBER(5,0),
    IS_ACTIVE BOOLEAN,

    SIGNUP_TIMESTAMP TIMESTAMP,
    LAST_LOGIN_TIME TIMESTAMP,

    ORDER_YEAR NUMBER(4,0),
    ORDER_MONTH NUMBER(2,0),
    ORDER_DAY NUMBER(2,0),

    TOTAL_ORDERS NUMBER(10,0),
    TOTAL_SPENT NUMBER(12,2),
    AVG_ORDER_VALUE NUMBER(10,2),

    DISCOUNT_PERCENT NUMBER(5,4),
    CONVERSION_RATE NUMBER(5,4),

    IS_RETURNED BOOLEAN,
    RETURN_REASON VARCHAR(100),

    PREFERRED_LANGUAGE VARCHAR(20),
    DEVICE_TYPE VARCHAR(20),
    BROWSER VARCHAR(50),

    IP_ADDRESS VARCHAR(50),
    COUNTRY VARCHAR(50),
    CURRENCY_CODE VARCHAR(10),

    LOYALTY_TIER VARCHAR(20),
    IS_SUBSCRIBED BOOLEAN,

    SUBSCRIPTION_START_DATE DATE,
    LAST_PURCHASE_DATE DATE,
    DAYS_SINCE_LAST_ORDER NUMBER(10,0),

    CREDIT_SCORE NUMBER(5,0),
    IS_FRAUD BOOLEAN,
    RISK_SCORE NUMBER(5,4),

    FEEDBACK_RATING NUMBER(3,1),
    FEEDBACK_COMMENT VARCHAR(255),

    JSON_METADATA VARCHAR(500),
    ARRAY_TAGS VARCHAR(255),

    GEO_LOCATION VARCHAR(50),

    CREATED_AT DATE,
    UPDATED_AT DATE
  ),

  column_descriptions (
    RECORD_ID = 'Primary key for enriched record',
    CUSTOMER_ID = 'Reference to customer',
    ORDER_ID = 'Reference to order',
    PRODUCT_ID = 'Reference to product',

    TOTAL_SPENT = 'Total customer spend (currency formatted)',
    DISCOUNT_PERCENT = 'Discount applied (0-1, semantic percent)',
    CONVERSION_RATE = 'Conversion rate (0-1, semantic percent)',

    IS_FRAUD = 'Fraud flag',
    RISK_SCORE = 'Risk probability score',

    JSON_METADATA = 'Semi-structured metadata',
    ARRAY_TAGS = 'Pipe-separated categorical tags',

    GEO_LOCATION = 'Latitude,Longitude format'
  ),

  column_tags (
    RECORD_ID = ('identifier', 'primary_key', 'grain'),

    CUSTOMER_ID = ('identifier', 'foreign_key'),
    ORDER_ID = ('identifier', 'foreign_key'),
    PRODUCT_ID = ('identifier', 'foreign_key'),

    TOTAL_SPENT = ('measure', 'monetary', 'currency'),
    AVG_ORDER_VALUE = ('measure', 'monetary'),

    DISCOUNT_PERCENT = ('measure', 'percentage'),
    CONVERSION_RATE = ('measure', 'percentage'),

    TOTAL_ORDERS = ('measure', 'count'),
    AGE = ('dimension', 'numeric'),

    IS_ACTIVE = ('dimension', 'boolean'),
    IS_FRAUD = ('dimension', 'risk_flag'),

    SIGNUP_TIMESTAMP = ('temporal', 'timestamp'),
    LAST_LOGIN_TIME = ('temporal', 'timestamp'),

    SUBSCRIPTION_START_DATE = ('temporal', 'date'),
    LAST_PURCHASE_DATE = ('temporal', 'date'),

    GEO_LOCATION = ('dimension', 'geo')
  ),

  column_terms (
    RECORD_ID = ('entity.identifier'),

    TOTAL_SPENT = ('revenue.metric'),
    AVG_ORDER_VALUE = ('sales.metric'),

    DISCOUNT_PERCENT = ('pricing.discount'),
    CONVERSION_RATE = ('marketing.conversion'),

    TOTAL_ORDERS = ('order.volume'),

    CUSTOMER_ID = ('customer.id'),
    ORDER_ID = ('order.id'),
    PRODUCT_ID = ('product.id')
  )
) ;


SELECT
  RECORD_ID,
  CUSTOMER_ID,
  ORDER_ID,
  PRODUCT_ID,

  FULL_NAME,
  CAST(AGE AS NUMBER) AS AGE,
  CAST(IS_ACTIVE AS BOOLEAN) AS IS_ACTIVE,

  CAST(SIGNUP_TIMESTAMP AS TIMESTAMP) AS SIGNUP_TIMESTAMP,
  CAST(LAST_LOGIN_TIME AS TIMESTAMP) AS LAST_LOGIN_TIME,

  ORDER_YEAR,
  ORDER_MONTH,
  ORDER_DAY,

  TOTAL_ORDERS,

  -- currency
  CAST(TOTAL_SPENT AS NUMBER(12,2)) AS TOTAL_SPENT,
  CAST(AVG_ORDER_VALUE AS NUMBER(10,2)) AS AVG_ORDER_VALUE,

  -- percent (IMPORTANT: keep 0-1, Cube formats later)
  CAST(DISCOUNT_PERCENT AS FLOAT) AS DISCOUNT_PERCENT,
  CAST(CONVERSION_RATE AS FLOAT) AS CONVERSION_RATE,

  CAST(IS_RETURNED AS BOOLEAN) AS IS_RETURNED,
  RETURN_REASON,

  PREFERRED_LANGUAGE,
  DEVICE_TYPE,
  BROWSER,

  IP_ADDRESS,
  COUNTRY,
  CURRENCY_CODE,

  LOYALTY_TIER,
  CAST(IS_SUBSCRIBED AS BOOLEAN) AS IS_SUBSCRIBED,

  CAST(SUBSCRIPTION_START_DATE AS DATE) AS SUBSCRIPTION_START_DATE,
  CAST(LAST_PURCHASE_DATE AS DATE) AS LAST_PURCHASE_DATE,
  DAYS_SINCE_LAST_ORDER,

  CREDIT_SCORE,
  CAST(IS_FRAUD AS BOOLEAN) AS IS_FRAUD,
  CAST(RISK_SCORE AS FLOAT) AS RISK_SCORE,

  FEEDBACK_RATING,
  FEEDBACK_COMMENT,

  JSON_METADATA,
  ARRAY_TAGS,
  GEO_LOCATION,

  CAST(CREATED_AT AS DATE) AS CREATED_AT,
  CAST(UPDATED_AT AS DATE) AS UPDATED_AT

FROM lenovo.raw.customer_orders_enriched