AUDIT (
  name regions_ext_name_consistency,
  blocking true
);

SELECT
  region_id,
  region_name,
  'Region name is outside the five sales regions' AS issue_type
FROM @this_model
WHERE region_name NOT IN ('North', 'South', 'East', 'West', 'Central');
