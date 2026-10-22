AUDIT (
  name order_status_lookup_consistency,
  blocking true
);

SELECT
  orders.order_id,
  orders.order_status,
  'Order status is missing from s3lhdepotrr.bronze_sparkv.order_status_lookup' AS issue_type
FROM @this_model AS orders
LEFT JOIN s3lhdepotrr.bronze_sparkv.order_status_lookup AS lookup
  ON orders.order_status = lookup.order_status
WHERE lookup.order_status IS NULL;
