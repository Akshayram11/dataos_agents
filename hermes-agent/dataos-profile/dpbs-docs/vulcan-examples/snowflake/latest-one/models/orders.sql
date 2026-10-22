MODEL (
  name lenovo.sales.orders,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column ORDER_DATE,
    forward_only true,
        on_destructive_change allow
  ),

  start '2024-01-01',
  cron '@daily',
  grain ORDER_ID,
  description 'Orders fact table with incremental loading by order date',
  tags ('orders', 'fact', 'sales_analytics'),
  terms ('sales.analytics', 'order.transactions'),
  columns (
    ORDER_ID VARCHAR(10),
    ORDER_DATE DATE,
    ORDER_DATE_TIMESTAMP TIMESTAMP,
    CUSTOMER_ID VARCHAR(10),
    PRODUCT_ID VARCHAR(10),
    QUANTITY NUMBER(38,0),
    UNIT_PRICE NUMBER(10,2),
    DISCOUNT NUMBER(5,2),
    TAX NUMBER(10,2),
    SHIPPING_COST NUMBER(10,2),
    TOTAL_AMOUNT NUMBER(10,2)
  ),
  column_descriptions (
    ORDER_ID = 'Unique identifier for each order',
    ORDER_DATE = 'Date when order was placed',
    CUSTOMER_ID = 'Reference to customer who placed the order',
    PRODUCT_ID = 'Reference to product ordered',
    QUANTITY = 'Quantity of items ordered',
    UNIT_PRICE = 'Price per unit at time of order',
    DISCOUNT = 'Discount rate applied (0.0-1.0)',
    TAX = 'Tax amount charged',
    SHIPPING_COST = 'Shipping cost for the order',
    TOTAL_AMOUNT = 'Total order amount including tax and shipping'
  ),
  column_tags (
    ORDER_ID = ('identifier', 'primary_key', 'grain'),
    ORDER_DATE = ('temporal', 'date', 'grain'),
    CUSTOMER_ID = ('identifier', 'foreign_key'),
    PRODUCT_ID = ('identifier', 'foreign_key'),
    QUANTITY = ('measure', 'count'),
    UNIT_PRICE = ('measure', 'monetary'),
    DISCOUNT = ('measure', 'ratio', 'percentage'),
    TAX = ('measure', 'monetary'),
    SHIPPING_COST = ('measure', 'monetary'),
    TOTAL_AMOUNT = ('measure', 'monetary', 'revenue')
  ),
  column_terms (
    ORDER_ID = ('entity.identifier', 'order.id'),
    ORDER_DATE = ('order.date', 'event.transaction'),
    TOTAL_AMOUNT = ('revenue.metric', 'sales.total'),
    QUANTITY = ('order.quantity', 'sales.volume')
  )
);

SELECT
  ORDER_ID,
  ORDER_DATE,
  CAST(ORDER_DATE AS TIMESTAMP) AS ORDER_DATE_TIMESTAMP,
  CUSTOMER_ID,
  PRODUCT_ID,
  QUANTITY,
  UNIT_PRICE,
  DISCOUNT,
  TAX,
  SHIPPING_COST,
  TOTAL_AMOUNT
FROM lenovo.raw.raw_orders
WHERE ORDER_DATE BETWEEN @start_date AND @end_date
