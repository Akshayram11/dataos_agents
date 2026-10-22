MODEL (
  name lenovo.raw.raw_customers,
  kind SEED (
    path '../../seeds/raw_customers.csv'
  ),
  description 'Seed model loading raw customer data from CSV file',
  tags ('seed', 'raw', 'customer', 'crm'),
  terms ('customer.profile', 'customer.segmentation'),
  columns (
    CUSTOMER_ID VARCHAR(10),
    FIRST_NAME VARCHAR(50),
    LAST_NAME VARCHAR(50),
    EMAIL VARCHAR(100),
    PHONE VARCHAR(20),
    ADDRESS_LINE1 VARCHAR(100),
    ADDRESS_LINE2 VARCHAR(100),
    CITY VARCHAR(50),
    STATE VARCHAR(50),
    POSTAL_CODE VARCHAR(20),
    CUSTOMER_SEGMENT VARCHAR(20),
    ACCOUNT_STATUS VARCHAR(20),
    SIGNUP_DATE DATE,
    LOYALTY_SCORE NUMBER(38,0)
  ),
  grain CUSTOMER_ID
);
