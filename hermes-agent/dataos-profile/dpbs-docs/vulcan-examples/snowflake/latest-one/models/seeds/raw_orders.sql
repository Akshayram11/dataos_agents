MODEL (
  name lenovo.raw.raw_orders,
  kind SEED (
    path '../../seeds/raw_orders.csv'
  ),
  description 'Seed model loading raw order data from CSV file',
  tags ('seed', 'raw', 'orders', 'sales_analytics'),
  terms ('sales.analytics', 'order.transactions'),
  columns (
    ORDER_ID VARCHAR(10),
    ORDER_DATE DATE,
    CUSTOMER_ID VARCHAR(10),
    PRODUCT_ID VARCHAR(10),
    QUANTITY NUMBER(38,0),
    UNIT_PRICE NUMBER(10,2),
    DISCOUNT NUMBER(5,2),
    TAX NUMBER(10,2),
    SHIPPING_COST NUMBER(10,2),
    TOTAL_AMOUNT NUMBER(10,2)
  ),
  grain ORDER_ID
);
