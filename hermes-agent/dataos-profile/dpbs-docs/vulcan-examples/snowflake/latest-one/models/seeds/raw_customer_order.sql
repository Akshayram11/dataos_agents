MODEL (
  name lenovo.raw.customer_orders_enriched,
  kind SEED (
    path '../../seeds/customer_orders_enriched.csv'
  ),
  description 'Seed model loading enriched customer, order, and product level data with all data types and formats',
  tags ('seed', 'raw', 'enriched', 'customer_orders', 'semantic_testing'),
  terms ('sales.analytics', 'customer.behavior', 'order.enrichment'),

  columns (
    RECORD_ID VARCHAR(10),
    CUSTOMER_ID VARCHAR(10),
    ORDER_ID VARCHAR(10),
    PRODUCT_ID VARCHAR(10),

    FULL_NAME VARCHAR(100),
    AGE NUMBER(5,0),
    IS_ACTIVE BOOLEAN,

    SIGNUP_TIMESTAMP VARCHAR(50),
    LAST_LOGIN_TIME VARCHAR(50),

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

  grain RECORD_ID
);