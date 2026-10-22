import typing as t
from datetime import datetime

import pandas as pd

from vulcan import ExecutionContext, model
from vulcan import ModelKindName


@model(
    "silverv1.customer_lifetime_value_py",
    columns={
        "customer_id": "int",
        "name": "text",
        "region_name": "text",
        "total_orders": "bigint",
        "total_items": "bigint",
        "total_spend": "double",
        "average_order_value": "double",
        "customer_lifetime_value": "double",
        "customer_segment": "text",
    },
    kind=dict(
        name=ModelKindName.FULL,
    ),
    grains=["customer_id"],
    depends_on=[
        "bronzev1.customers",
        "bronzev1.orders",
        "bronzev1.order_items",
        "bronzev1.regions",
    ],
    tags=["silver", "customer", "python", "analytics"],
    description="Customer lifetime value and customer segmentation calculated using Python.",
)
def execute(
    context: ExecutionContext,
    start: datetime,
    end: datetime,
    execution_time: datetime,
    **kwargs: t.Any,
) -> pd.DataFrame:

    customers = context.resolve_table("bronzev1.customers")
    orders = context.resolve_table("bronzev1.orders")
    order_items = context.resolve_table("bronzev1.order_items")
    regions = context.resolve_table("bronzev1.regions")

    query = f"""
        SELECT
            c.customer_id,
            c.name,
            r.region_name,
            COUNT(DISTINCT o.order_id) AS total_orders,
            COALESCE(SUM(oi.quantity), 0) AS total_items,
            COALESCE(
                SUM(oi.quantity * oi.unit_price),
                0
            ) AS total_spend
        FROM {customers} c
        LEFT JOIN {regions} r
            ON c.region_id = r.region_id
        LEFT JOIN {orders} o
            ON c.customer_id = o.customer_id
        LEFT JOIN {order_items} oi
            ON o.order_id = oi.order_id
        GROUP BY
            c.customer_id,
            c.name,
            r.region_name
    """

    df = context.fetchdf(query)

    # Python business logic
    df["total_spend"] = df["total_spend"].fillna(0)
    df["total_orders"] = df["total_orders"].fillna(0)
    df["total_items"] = df["total_items"].fillna(0)

    df["average_order_value"] = (
        df["total_spend"] / df["total_orders"].replace(0, 1)
    )

    # Simple CLV estimation:
    # historical spend + expected future value based on order frequency
    df["customer_lifetime_value"] = (
        df["average_order_value"]
        * df["total_orders"]
        * 1.25
    )

    def classify_customer(row):
        if row["customer_lifetime_value"] >= 10000:
            return "VIP"
        elif row["total_orders"] >= 10:
            return "Loyal"
        elif row["total_orders"] >= 3:
            return "Regular"
        else:
            return "At Risk"

    df["customer_segment"] = df.apply(
        classify_customer,
        axis=1,
    )

    return df