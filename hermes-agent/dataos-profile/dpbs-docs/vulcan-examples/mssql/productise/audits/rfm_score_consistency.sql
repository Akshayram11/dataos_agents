AUDIT (
  name rfm_score_consistency,
  blocking true
);

SELECT
  customer_id,
  recency_score,
  frequency_score,
  monetary_score,
  rfm_score,
  rfm_segment,
  'RFM score or segment is inconsistent' AS issue_type
FROM @this_model
WHERE recency_score NOT BETWEEN 1 AND 5
   OR frequency_score NOT BETWEEN 1 AND 5
   OR monetary_score NOT BETWEEN 1 AND 5
   OR rfm_score <> CONCAT(recency_score, frequency_score, monetary_score)
   OR rfm_segment NOT IN (
     'Champions',
     'Loyal Customers',
     'Potential Loyalists',
     'Recent Customers',
     'Promising',
     'Customers Needing Attention',
     'At Risk',
     'Hibernating',
     'Lost'
   );
