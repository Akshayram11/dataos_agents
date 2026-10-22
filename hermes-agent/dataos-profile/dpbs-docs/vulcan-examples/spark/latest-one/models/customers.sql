MODEL (
  name sales.customers,
  kind FULL,
  cron '@daily',
  grain customer_id,
  description 'Customer dimension table with full refresh',
  tags ('customer', 'dimension', 'crm'),
  terms ('customer.profile', 'customer.segmentation'),
  -- audits (
  --   validate_customer_id,
  --   skip true
  -- ),
  columns (
    customer_id VARCHAR(10),
    full_name VARCHAR(101),
    email VARCHAR(100),
    phone VARCHAR(20),
    address_line VARCHAR(300),
    customer_segment VARCHAR(20),
    account_status VARCHAR(20),
    signup_date DATE,
    signup_timestamp TIMESTAMP,
    loyalty_score INT
  ),
  column_descriptions (
    customer_id = 'Unique identifier for each customer',
    full_name = 'Customer full name',
    email = 'Customer email address',
    phone = 'Customer phone number',
    address_line = 'Full address including street, city, state, and postal code',
    customer_segment = 'Customer segment tier (Platinum, Gold, Silver, Bronze)',
    account_status = 'Account status (Active, Inactive, Suspended)',
    signup_date = 'Date when customer signed up',
    signup_timestamp = 'Timestamp when customer signed up (cast from signup_date)',
    loyalty_score = 'Customer loyalty score'
  ),
  column_tags (
    customer_id = ('identifier', 'primary_key', 'grain'),
    full_name = ('dimension', 'pii'),
    email = ('dimension', 'pii', 'contact'),
    phone = ('dimension', 'pii', 'contact'),
    address_line = ('dimension', 'pii', 'location'),
    customer_segment = ('dimension', 'classification', 'tier'),
    account_status = ('dimension', 'status'),
    signup_date = ('temporal', 'date', 'milestone'),
    signup_timestamp = ('temporal', 'timestamp', 'milestone'),
    loyalty_score = ('measure', 'metric', 'behavioral')
  ),
  column_terms (
    customer_id = ('entity.identifier', 'customer.account_id'),
    customer_segment = ('customer.segment', 'classification.tier'),
    signup_date = ('customer.activation', 'event.signup'),
    loyalty_score = ('customer.loyalty', 'behavioral.metric')
  ),
  column_mask_expressions (
    email = '***redacted***'

  ),
  column_classifications (
    email = restricted
  )
);

SELECT
  customer_id,
  CONCAT(first_name, ' ', last_name) AS full_name,
  email,
  phone,
  CONCAT(address_line1, ' ', COALESCE(address_line2, ''), ' ', city, ' ', state, ' ', postal_code) AS address_line,
  customer_segment,
  account_status,
  signup_date,
  CAST(signup_date AS TIMESTAMP) AS signup_timestamp,
  loyalty_score
FROM raw.raw_customers
