---
description: >-
  Build and run an RFM customer-segmentation model with Snowpark Python on
  Snowflake.
---

# Use Snowpark Python Models

## Overview

This recipe builds an RFM customer-segmentation table with a Snowpark Python model. It reads `sales.customer_profile` and assigns recency, frequency, monetary, and tier scores.

Use Snowpark when chained DataFrame operations are clearer than a single SQL query.

{% hint style="info" %}
**Prerequisites**

* A Snowflake account, warehouse, and a user/role Vulcan can connect as (key-pair, username/password, or another supported [authentication method](../))
* `USAGE` on the warehouse, database, and source schema
* `SELECT` on the source table and write access on the target schema
{% endhint %}

## Steps

{% stepper %}
{% step %}
### Configure the Snowflake engine connection

`config.yaml` has to point Vulcan at Snowflake before any model can run:

```yaml
gateways:
  default:
    connection:
      type: snowflake
      account: <org>-<account>          # from your Snowflake console URL
      user: <vulcan_user>
      authenticator: snowflake_jwt
      private_key_path: ./snowflake_key.p8
      private_key_passphrase: <YOUR_PASSPHRASE>
      warehouse: <warehouse>
      database: <database>
      role: <role>
    state_connection:
      type: duckdb                      # local dev only
      database: ./state.duckdb

model_defaults:
  dialect: snowflake
  start: '2025-01-01'
```

`type: snowflake` and `model_defaults.dialect: snowflake` compile the model in step 5 for Snowflake. They also provide its `context.snowpark` session.

{% hint style="info" %}
Run the commands in this recipe from the project root. Keep private keys outside version control.
{% endhint %}
{% endstep %}

{% step %}
### Create sample customer data

For this demonstration, `config.yaml` creates test data. Use an existing source table in production.

(config.yaml)

```yaml
# INITIAL SETUP
before_all:

  - USE DATABASE DEMO_DB;

  - CREATE SCHEMA IF NOT EXISTS RAW;

  - CREATE SCHEMA IF NOT EXISTS SALES;

  - USE SCHEMA SALES;

  # Source table
  - |
    CREATE TABLE IF NOT EXISTS RAW.RAW_CUSTOMERS (
      CUSTOMER_ID INTEGER,
      CUSTOMER_NAME STRING,
      EMAIL STRING,
      REGION_ID INTEGER,
      REGION_NAME STRING,
      CUSTOMER_SEGMENT STRING,
      LAST_ORDER_DATE DATE,
      TOTAL_ORDERS INTEGER,
      TOTAL_SPEND NUMBER(12,2)
    );

  # Seed data
  - |
    INSERT INTO RAW.RAW_CUSTOMERS (
      CUSTOMER_ID,
      CUSTOMER_NAME,
      EMAIL,
      REGION_ID,
      REGION_NAME,
      CUSTOMER_SEGMENT,
      LAST_ORDER_DATE,
      TOTAL_ORDERS,
      TOTAL_SPEND
    )
    SELECT *
    FROM (
      VALUES
      (1,'John Smith','john@example.com',1,'East','High Value','2025-05-18',24,15230),
      (2,'Alice Brown','alice@example.com',2,'West','Medium Value','2025-05-20',13,8420),
      (3,'Bob Wilson','bob@example.com',1,'East','Low Value','2025-05-09',4,920),
      (4,'Emma Davis','emma@example.com',3,'North','High Value','2025-05-21',39,28800),
      (5,'David Miller','david@example.com',2,'West','Medium Value','2025-05-11',9,4200),
      (6,'Sophia Taylor','sophia@example.com',1,'East','High Value','2025-05-22',44,34210)
    ) seed (
      CUSTOMER_ID,
      CUSTOMER_NAME,
      EMAIL,
      REGION_ID,
      REGION_NAME,
      CUSTOMER_SEGMENT,
      LAST_ORDER_DATE,
      TOTAL_ORDERS,
      TOTAL_SPEND
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM RAW.RAW_CUSTOMERS
    );
```
{% endstep %}

{% step %}
### Create model

The scoring model reads the seeded customer table. Save this file in the project's `models` directory.

(customer\_profile.sql)

```sql
MODEL (
  name sales.customer_profile,
  kind FULL,
  grains [CUSTOMER_ID],
  description 'Customer profile used as input for RFM scoring.'
);

SELECT
  CUSTOMER_ID,
  CUSTOMER_NAME,
  EMAIL,
  REGION_ID,
  REGION_NAME,
  CUSTOMER_SEGMENT,
  LAST_ORDER_DATE,
  TOTAL_ORDERS,
  TOTAL_SPEND
FROM RAW.RAW_CUSTOMERS;
```
{% endstep %}

{% step %}
### Resolve the upstream model

Add this code to `rfm_customer_segmentation.py`:

```python
customer_profile = context.resolve_table("sales.customer_profile")
customers = session.table(customer_profile)
```

`context.resolve_table` looks up the physical table Vulcan actually materialized for `sales.customer_profile`, rather than assuming a fixed name, this keeps the Snowpark model correct across environments (dev/prod schemas, versioned table names) without hardcoding anything.
{% endstep %}

{% step %}
### Build RFM scores

Continue in `rfm_customer_segmentation.py`:

```python
from vulcan import ExecutionContext, model
from vulcan import ModelKindName


@model(
    "sales.rfm_customer_segmentation",
    kind=dict(
        name=ModelKindName.FULL,
    ),
    grains=["CUSTOMER_ID"],
    columns={
        "CUSTOMER_ID": "INT",
        "CUSTOMER_NAME": "STRING",
        "EMAIL": "STRING",
        "REGION_NAME": "STRING",
        "TOTAL_SPEND": "NUMBER(12,2)",
        "TOTAL_ORDERS": "INT",
        "LAST_ORDER_DATE": "TIMESTAMP",
        "RECENCY_DAYS": "INT",
        "RECENCY_SCORE": "INT",
        "FREQUENCY_SCORE": "INT",
        "MONETARY_SCORE": "INT",
        "RFM_SCORE": "INT",
        "CUSTOMER_TIER": "STRING",
    },
    description="""
    Demonstrates Snowpark Python by computing customer
    RFM (Recency, Frequency, Monetary) segmentation
    using Snowpark DataFrames.
    """,
)
def execute(context: ExecutionContext, **kwargs):
    # Snowpark functions imported INSIDE execute() — importing at module
    # scope raises `NameError: 'col' is not defined` on Snowflake.
    from snowflake.snowpark import Session
    from snowflake.snowpark.functions import col, current_date, datediff, lit, when

    session: Session = context.snowpark
    customer_profile = context.resolve_table("sales.customer_profile")
    customers = session.table(customer_profile)

    # Recency
    customers = customers.with_column(
        "RECENCY_DAYS",
        datediff("day", col("LAST_ORDER_DATE"), current_date()),
    )
    customers = customers.with_column(
        "RECENCY_SCORE",
        when(col("RECENCY_DAYS") <= 30, lit(5))
        .when(col("RECENCY_DAYS") <= 60, lit(4))
        .when(col("RECENCY_DAYS") <= 90, lit(3))
        .when(col("RECENCY_DAYS") <= 180, lit(2))
        .otherwise(lit(1)),
    )

    # Frequency
    customers = customers.with_column(
        "FREQUENCY_SCORE",
        when(col("TOTAL_ORDERS") >= 40, lit(5))
        .when(col("TOTAL_ORDERS") >= 25, lit(4))
        .when(col("TOTAL_ORDERS") >= 15, lit(3))
        .when(col("TOTAL_ORDERS") >= 8, lit(2))
        .otherwise(lit(1)),
    )

    # Monetary
    customers = customers.with_column(
        "MONETARY_SCORE",
        when(col("TOTAL_SPEND") >= 30000, lit(5))
        .when(col("TOTAL_SPEND") >= 20000, lit(4))
        .when(col("TOTAL_SPEND") >= 10000, lit(3))
        .when(col("TOTAL_SPEND") >= 5000, lit(2))
        .otherwise(lit(1)),
    )

    # Overall RFM score and tier
    customers = customers.with_column(
        "RFM_SCORE",
        col("RECENCY_SCORE") + col("FREQUENCY_SCORE") + col("MONETARY_SCORE"),
    )
    customers = customers.with_column(
        "CUSTOMER_TIER",
        when(col("RFM_SCORE") >= 13, lit("Platinum"))
        .when(col("RFM_SCORE") >= 10, lit("Gold"))
        .when(col("RFM_SCORE") >= 7, lit("Silver"))
        .otherwise(lit("Bronze")),
    )

    return customers.select(
        "CUSTOMER_ID",
        "CUSTOMER_NAME",
        "EMAIL",
        "REGION_NAME",
        "TOTAL_SPEND",
        "TOTAL_ORDERS",
        col("LAST_ORDER_DATE").cast("TIMESTAMP").alias("LAST_ORDER_DATE"),
        "RECENCY_DAYS",
        "RECENCY_SCORE",
        "FREQUENCY_SCORE",
        "MONETARY_SCORE",
        "RFM_SCORE",
        "CUSTOMER_TIER",
    )
```

Each `with_column` call adds exactly one derived field: recency, frequency, monetary, the combined score, or the tier. Readers can trace which block produced each column instead of parsing one large nested expression.

{% hint style="info" %}
The score thresholds are examples. Profile your customer data before production use.
{% endhint %}
{% endstep %}

{% step %}
### Apply and run

```bash
vulcan plan
vulcan run
```

`vulcan plan` validates the project and shows the planned changes. `vulcan run` executes the models.

Resolve plan errors before running the model.
{% endstep %}

{% step %}
### Verify in Snowflake

Vulcan's run history confirms the model executed; it doesn't confirm the scoring logic produced sane output. Connect directly and check the result:

```bash
snowsql \
  -a <account_identifier> \
  -u <username> \
  -r <role> \
  -w <warehouse> \
  -d <database> \
  -s SALES \
  --private-key-path <path_to_private_key>
```

Confirm the model built and spot-check the tier distribution:

```sql
SELECT * FROM SALES.RFM_CUSTOMER_SEGMENTATION LIMIT 10;

SELECT CUSTOMER_TIER, COUNT(*) AS customer_count
FROM SALES.RFM_CUSTOMER_SEGMENTATION
GROUP BY CUSTOMER_TIER
ORDER BY customer_count DESC;
```

Expect one row per `CUSTOMER_ID`. Expect scores from `1` to `5`, an `RFM_SCORE` from `3` to `15`, and a tier from `Bronze` to `Platinum`.

If every row lands in the same tier, the thresholds in step 5 do not match the data. Sanity-check with:

```sql
SELECT CUSTOMER_ID, RECENCY_SCORE, FREQUENCY_SCORE, MONETARY_SCORE, RFM_SCORE, CUSTOMER_TIER
FROM SALES.RFM_CUSTOMER_SEGMENTATION
ORDER BY RFM_SCORE DESC;
```
{% endstep %}
{% endstepper %}

## Troubleshooting

| Symptom                                                            | Cause                                                                                                  | Resolution                                                                                                   |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Snowpark model runs noticeably slower than an equivalent SQL model | Warehouse undersized for Python execution                                                              | Size the warehouse up one step                                                                               |
| `context.resolve_table` raises or returns an unexpected name       | `sales.customer_profile` hasn't been planned/applied yet in this environment, or the model was renamed | Confirm `vulcan plan` has run for `sales.customer_profile` in the same environment before running this model |

## References

* [Snowflake engine guide: Python (Snowpark) models](../): The module-scope import failure mode, documented verbatim.
* [Model types: Python](../../../models/data-models/types/python.md)
* [Model kinds: FULL](../../../models/data-models/model-kinds.md#full): This model uses `kind FULL`, the same portable kind a SQL model would use. Only the language and compute (`context.snowpark`) are Snowflake-specific.

## Download the complete project

{% file src="../../../.gitbook/assets/sf-dp-example.zip" %}
