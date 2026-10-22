---
description: >-
  How Write-Audit-Publish keeps bad data out of production: write to the model, run blocking assertions, publish only if they pass.
---

# Write-Audit-Publish

Write-Audit-Publish (WAP) is a 3-step pattern for shipping data changes without risking the Data Product's consumption. It **writes** the new or changed data to the model, **audits** that model against a set of rules, and **publishes** it to production only if every rule passes.

{% hint style="success" %}
**Put the checks where they pay off**

WAP doesn't mean checking everything everywhere. The pattern works best when the heavy checks sit on the layer that first turns raw data into something trustworthy, not on every layer built on top of it. Once that layer has proven itself, downstream models can build on it without re-deriving the same trust.
{% endhint %}


You don't build this pattern by hand in Vulcan. It's what already happens whenever you run `vulcan plan` against models that define [Assertions](../quality/assertions.md). Vulcan writes each model to a fresh physical table, runs that model's assertions against it, and only swaps production over once every blocking assertion has passed. See [Architecture](architecture.md) for how this fits into the fingerprint-plan-apply flow, and [Run and plan](run-and-plan/README.md) for what `vulcan plan` does step by step.


## Example: the Orders pipeline

Here's what WAP looks like in a real pipeline: order data moving from a raw source, through cleaning, into a table that powers a revenue dashboard.

The pipeline has 3 tables:

* `bronze.orders` - the raw data, straight from the source, warts and all.
* `silver.orders` - the same data, cleaned up and deduplicated.
* `gold.revenue_by_day` - the number the dashboard actually shows.

All the serious quality checks sit on silver, not gold. By the time gold reads from silver, the data has already been proven trustworthy, so gold doesn't need to defend itself against bad data, because it never sees any.

### Bronze: land the data

Bronze doesn't try to be clever. It ingests whatever the source system sends, duplicates included. The only check here is a basic sanity check: did any rows show up today?

```sql
MODEL (
  name bronze.orders,
  kind FULL,
  cron '@daily',
  assertions (
    number_of_rows(threshold := 0)
  )
);

SELECT order_id, order_date, region_id, revenue, _ingested_at
FROM raw.orders_landing;
```

### Silver: where the real checking happens

This is the important layer. Silver cleans the data, dropping nulls and deduplicating orders, and then runs a set of blocking assertions before the result is allowed to publish anywhere.

```sql
MODEL (
  name silver.orders,
  kind FULL,
  cron '@daily',
  grains (order_id),
  assertions (
    number_of_rows(threshold := 0),
    not_null(columns := (order_date, region_id, revenue)),
    unique_combination_of_columns(columns := (order_id)),
    accepted_range(column := revenue, min_v := 0),
    silver_orders_reconciles_with_bronze
  )
);

SELECT order_id, order_date, region_id, revenue
FROM bronze.orders
WHERE order_id IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC) = 1;
```

The last assertion in that list, `silver_orders_reconciles_with_bronze`, points at a custom audit defined separately. It compares silver back against bronze to make sure no orders quietly disappeared during cleaning:

```sql
-- audits/silver_orders_reconciles_with_bronze.sql
AUDIT (name silver_orders_reconciles_with_bronze);

SELECT b.order_id
FROM bronze.orders AS b
LEFT JOIN silver.orders AS s ON b.order_id = s.order_id
WHERE b.order_id IS NOT NULL AND s.order_id IS NULL;
```

Every assertion on this model is blocking: if any of them fail, silver doesn't publish, and neither does anything downstream of it.

### Gold: just do the math

Because silver already did the hard work of validating the data, gold stays simple. It's a sum, grouped by day and region, with no assertions needed.

```sql
MODEL (
  name gold.revenue_by_day,
  kind FULL,
  cron '@daily',
  grains (order_date, region_id)
);

SELECT order_date, region_id, SUM(revenue) AS total_revenue
FROM silver.orders
GROUP BY 1, 2;
```

## From plan to publish

```bash
vulcan plan
```

Vulcan first writes a fresh version of each model; nothing touches production yet. Then it runs the assertions on bronze and silver. Only if every blocking assertion passes does it swap production over to the new tables, layer by layer: bronze, then silver, then gold.

If any assertion fails, the whole plan stops. Nothing publishes, at any layer. The dashboard keeps showing yesterday's numbers, untouched, until someone fixes the problem and reruns the pipeline.

This is why the pattern pays off beyond any single run:

* Checking once at silver protects every model built on top of it, not just one dashboard.
* Gold models stay simple because they inherit trust from silver instead of re-deriving it.
* A failed check fails loudly and early, at the layer that produced the problem, instead of silently corrupting a downstream table.

## Where to go next

* [Assertions](../quality/assertions.md) - the blocking rules that make Write-Audit-Publish work.
* [Architecture](architecture.md) - the fingerprint-plan-apply flow that Write-Audit-Publish runs on.
* [Run and plan](run-and-plan/README.md) - what `vulcan plan` does step by step, including how it decides what to write and when to publish.
