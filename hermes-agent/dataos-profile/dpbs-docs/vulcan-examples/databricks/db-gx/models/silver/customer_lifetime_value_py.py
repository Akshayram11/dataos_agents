import typing as t
from datetime import datetime

import pandas as pd

from vulcan import ExecutionContext, model
from vulcan import ModelKindName


@model(
    "silverv1.customer_lifetime_value_py",
    columns={
        "customer_id": "string",
        "customer_name": "string",
        "region_name": "string",
        "total_orders": "bigint",
        "total_items": "bigint",
        "total_spend": "decimal(18,2)",
        "average_order_value": "decimal(18,2)",
        "customer_lifetime_value": "decimal(18,2)",
    },
    kind=dict(name=ModelKindName.FULL),
    grains=["customer_id"],
    depends_on=[
        "bronzev1.customers",
        "bronzev1.orders",
        "bronzev1.order_items",
        "bronzev1.regions",
    ],
    tags=["silver", "python"],
    description="Simple customer lifetime value model.",
)
def execute(
    context: ExecutionContext,
    start: datetime,
    end: datetime,
    execution_time: datetime,
    **kwargs: t.Any,
) -> pd.DataFrame:

    customers = context.resolve_table(
        "bronzev1.customers"
    )

    orders = context.resolve_table(
        "bronzev1.orders"
    )

    order_items = context.resolve_table(
        "bronzev1.order_items"
    )

    regions = context.resolve_table(
        "bronzev1.regions"
    )

    query = f"""
        SELECT
            c.customer_id,
            c.name AS customer_name,
            r.region_name,

            COUNT(DISTINCT o.order_id) AS total_orders,

            COALESCE(
                SUM(oi.quantity),
                0
            ) AS total_items,

            COALESCE(
                SUM(
                    oi.quantity * oi.unit_price
                ),
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

    result = context.fetchdf(query)

    result["total_orders"] = pd.to_numeric(
        result["total_orders"]
    ).fillna(0)

    result["total_items"] = pd.to_numeric(
        result["total_items"]
    ).fillna(0)

    result["total_spend"] = pd.to_numeric(
        result["total_spend"]
    ).fillna(0)

    result["average_order_value"] = (
        result["total_spend"]
        .div(result["total_orders"].replace(0, pd.NA))
        .fillna(0)
        .round(2)
    )

    result["customer_lifetime_value"] = (
        result["average_order_value"]
    )

    result["total_orders"] = (
        result["total_orders"]
        .astype("int64")
    )

    result["total_items"] = (
        result["total_items"]
        .astype("int64")
    )

    result["total_spend"] = (
        result["total_spend"]
        .round(2)
    )

    result["average_order_value"] = (
        result["average_order_value"]
        .round(2)
    )

    result["customer_lifetime_value"] = (
        result["customer_lifetime_value"]
        .round(2)
    )

    return result[
        [
            "customer_id",
            "customer_name",
            "region_name",
            "total_orders",
            "total_items",
            "total_spend",
            "average_order_value",
            "customer_lifetime_value",
        ]
    ]