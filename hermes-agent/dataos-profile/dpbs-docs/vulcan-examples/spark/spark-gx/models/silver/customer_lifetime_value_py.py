from datetime import datetime
import typing as t

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from vulcan import ExecutionContext, model
from vulcan import ModelKindName


@model(
    "s3lhdepotrr.silver_sparkv.customer_lifetime_value_py",
    columns={
        "customer_id": "int",
        "customer_name": "text",
        "region_name": "text",
        "total_orders": "bigint",
        "total_spend": "double",
    },
    kind=dict(
        name=ModelKindName.FULL,
    ),
    grains=["customer_id"],
    depends_on=[
        "s3lhdepotrr.bronze_sparkv.customers",
        "s3lhdepotrr.bronze_sparkv.orders",
        "s3lhdepotrr.bronze_sparkv.order_items",
        "s3lhdepotrr.bronze_sparkv.regions",
    ],
    tags=["silver", "customer", "python"],
    description="Simple customer order summary calculated using PySpark.",
)
def execute(
    context: ExecutionContext,
    start: datetime,
    end: datetime,
    execution_time: datetime,
    **kwargs: t.Any,
) -> DataFrame:

    customers = context.resolve_table("s3lhdepotrr.bronze_sparkv.customers")
    orders = context.resolve_table("s3lhdepotrr.bronze_sparkv.orders")
    order_items = context.resolve_table("s3lhdepotrr.bronze_sparkv.order_items")
    regions = context.resolve_table("s3lhdepotrr.bronze_sparkv.regions")

    customers_df = context.spark.table(customers)
    orders_df = context.spark.table(orders)
    order_items_df = context.spark.table(order_items)
    regions_df = context.spark.table(regions)

    result = (
        customers_df.alias("c")
        .join(
            regions_df.alias("r"),
            F.col("c.region_id") == F.col("r.region_id"),
            "left",
        )
        .join(
            orders_df.alias("o"),
            F.col("c.customer_id") == F.col("o.customer_id"),
            "left",
        )
        .join(
            order_items_df.alias("oi"),
            F.col("o.order_id") == F.col("oi.order_id"),
            "left",
        )
        .groupBy(
            F.col("c.customer_id"),
            F.col("c.name"),
            F.col("r.region_name"),
        )
        .agg(
            F.countDistinct("o.order_id").cast("bigint").alias("total_orders"),
            F.coalesce(
                F.sum(
                    F.col("oi.quantity") * F.col("oi.unit_price")
                ),
                F.lit(0),
            ).cast("double").alias("total_spend"),
        )
        .select(
            F.col("customer_id"),
            F.col("name").alias("customer_name"),
            F.col("region_name"),
            F.col("total_orders"),
            F.col("total_spend"),
        )
    )

    return result