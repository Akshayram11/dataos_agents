AUDIT (
  name daily_sales_metric_consistency,
  blocking true
);

SELECT
  order_date,
  region_id,
  customer_id,
  product_id,
  total_orders,
  total_revenue,
  avg_order_value,
  shipment_rate,
  'Daily sales derived metrics are inconsistent' AS issue_type
FROM @this_model
WHERE total_orders <= 0
   OR total_items_sold < 0
   OR total_revenue < 0
   OR total_shipments < 0
   OR shipment_rate < 0
   OR shipment_rate > 1
   OR ROUND(total_revenue / NULLIF(total_orders, 0), 2) <> avg_order_value;
