MODEL (
  name lenovo.sales.customers,
  kind FULL,
  cron '@daily',
  grain CUSTOMER_ID,
  description 'Customer dimension table with full refresh',
  tags ('customer', 'dimension', 'crm'),
  terms ('customer.profile', 'customer.segmentation'),
  -- audits (
  --   validate_customer_id,
  --   skip true
  -- ),
  columns (
    CUSTOMER_ID VARCHAR(10),
    FULL_NAME VARCHAR(101),
    EMAIL VARCHAR(100),
    PHONE VARCHAR(20),
    ADDRESS_LINE VARCHAR(300),
    CUSTOMER_SEGMENT VARCHAR(20),
    ACCOUNT_STATUS VARCHAR(20),
    SIGNUP_DATE DATE,
    SIGNUP_TIMESTAMP TIMESTAMP,
    LOYALTY_SCORE NUMBER(38,0)
  ),
  column_descriptions (
    CUSTOMER_ID = 'Unique identifier for each customer',
    FULL_NAME = 'Customer full name',
    EMAIL = 'Customer email address',
    PHONE = 'Customer phone number',
    ADDRESS_LINE = 'Full address including street, city, state, and postal code',
    CUSTOMER_SEGMENT = 'Customer segment tier (Platinum, Gold, Silver, Bronze)',
    ACCOUNT_STATUS = 'Account status (Active, Inactive, Suspended)',
    SIGNUP_DATE = 'Date when customer signed up',
    SIGNUP_TIMESTAMP = 'Timestamp when customer signed up (cast from SIGNUP_DATE)',
    LOYALTY_SCORE = 'Customer loyalty score'
  ),
  column_tags (
    CUSTOMER_ID = ('identifier', 'primary_key', 'grain'),
    FULL_NAME = ('dimension', 'pii'),
    EMAIL = ('dimension', 'pii', 'contact'),
    PHONE = ('dimension', 'pii', 'contact'),
    ADDRESS_LINE = ('dimension', 'pii', 'location'),
    CUSTOMER_SEGMENT = ('dimension', 'classification', 'tier'),
    ACCOUNT_STATUS = ('dimension', 'status'),
    SIGNUP_DATE = ('temporal', 'date', 'milestone'),
    SIGNUP_TIMESTAMP = ('temporal', 'timestamp', 'milestone'),
    LOYALTY_SCORE = ('measure', 'metric', 'behavioral')
  ),
  column_terms (
    CUSTOMER_ID = ('entity.identifier', 'customer.account_id'),
    CUSTOMER_SEGMENT = ('customer.segment', 'classification.tier'),
    SIGNUP_DATE = ('customer.activation', 'event.signup'),
    LOYALTY_SCORE = ('customer.loyalty', 'behavioral.metric')
  ),
  column_mask_expressions (
    EMAIL = '***redacted***'

  ),
  column_classifications (
    EMAIL = restricted
  )
);

SELECT
  CUSTOMER_ID,
  CONCAT(FIRST_NAME, ' ', LAST_NAME) AS FULL_NAME,
  EMAIL,
  PHONE,
  CONCAT(ADDRESS_LINE1, ' ', COALESCE(ADDRESS_LINE2, ''), ' ', CITY, ' ', STATE, ' ', POSTAL_CODE) AS ADDRESS_LINE,
  CUSTOMER_SEGMENT,
  ACCOUNT_STATUS,
  SIGNUP_DATE,
  CAST(SIGNUP_DATE AS TIMESTAMP) AS SIGNUP_TIMESTAMP,
  LOYALTY_SCORE
FROM lenovo.raw.raw_customers
