MODEL (
  name raw.raw_orders,
  kind SEED (
    path '../../seeds/raw_orders.csv'
  ),
  description 'Seed model loading raw order data from csv file',
  tags ('seed', 'raw', 'orders', 'sales_analytics'),
  terms ('sales.analytics', 'order.transactions'),
  columns (
    order_id VARCHAR(10),
    order_date DATE,
    customer_id VARCHAR(10),
    product_id VARCHAR(10),
    quantity NUMBER(38,0),
    unit_price NUMBER(10,2),
    discount NUMBER(5,2),
    tax NUMBER(10,2),
    shipping_cost NUMBER(10,2),
    total_amount NUMBER(10,2)
  ),
  grain order_id
);
