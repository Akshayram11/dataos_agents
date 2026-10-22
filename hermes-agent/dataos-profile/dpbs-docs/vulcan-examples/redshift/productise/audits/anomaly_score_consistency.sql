AUDIT (
  name anomaly_score_consistency,
  blocking true
);

SELECT
    order_date,
    region_name,
    daily_revenue,
    rolling_average,
    rolling_std_dev,
    z_score,
    is_anomaly,
    'Invalid anomaly calculation' AS issue_type
FROM @this_model
WHERE rolling_average < 0
   OR rolling_std_dev < 0
   OR (is_anomaly = TRUE AND ABS(z_score) <= 3)
   OR (is_anomaly = FALSE AND ABS(z_score) > 3);