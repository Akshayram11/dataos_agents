MODEL (
  name sales.orders,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column order_date,
    forward_only true,
        on_destructive_change allow
  ),

  start '2024-01-01',
  cron '@daily',
  grain order_id,
  description 'Orders fact table with incremental loading by order date',
  tags ('orders', 'fact', 'sales_analytics'),
  terms ('sales.analytics', 'order.transactions'),
  columns (
    order_id VARCHAR(10),
    order_date DATE,
    order_date_timestamp DATETIME,
    customer_id VARCHAR(10),
    product_id VARCHAR(10),
    quantity NUMERIC(38,0),
    unit_price NUMERIC(10,2),
    discount NUMERIC(5,2),
    tax NUMERIC(10,2),
    shipping_cost NUMERIC(10,2),
    total_amount NUMERIC(10,2)
  ),
  column_descriptions (
    order_id = 'Unique identifier for each order',
    order_date = 'Date when order was placed',
    customer_id = 'Reference to customer who placed the order',
    product_id = 'Reference to product ordered',
    quantity = 'Quantity of items ordered',
    unit_price = 'Price per unit at time of order',
    discount = 'Discount rate applied (0.0-1.0)',
    tax = 'Tax amount charged',
    shipping_cost = 'Shipping cost for the order',
    total_amount = 'Total order amount including tax and shipping'
  ),
  column_tags (
    order_id = ('identifier', 'primary_key', 'grain'),
    order_date = ('temporal', 'date', 'grain'),
    customer_id = ('identifier', 'foreign_key'),
    product_id = ('identifier', 'foreign_key'),
    quantity = ('measure', 'count'),
    unit_price = ('measure', 'monetary'),
    discount = ('measure', 'ratio', 'percentage'),
    tax = ('measure', 'monetary'),
    shipping_cost = ('measure', 'monetary'),
    total_amount = ('measure', 'monetary', 'revenue')
  ),
  column_terms (
    order_id = ('entity.identifier', 'order.id'),
    order_date = ('order.date', 'event.transaction'),
    total_amount = ('revenue.metric', 'sales.total'),
    quantity = ('order.quantity', 'sales.volume')
  )
);

SELECT
  order_id,
  order_date,
  CAST(order_date AS DATETIME) AS order_date_timestamp,
  customer_id,
  product_id,
  quantity,
  unit_price,
  discount,
  tax,
  shipping_cost,
  total_amount
FROM raw.raw_orders
WHERE order_date BETWEEN @start_date AND @end_date
