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
    quantity INT,
    unit_price DOUBLE,
    discount DOUBLE,
    tax DOUBLE,
    shipping_cost DOUBLE,
    total_amount DOUBLE
  ),
  grain order_id
);
