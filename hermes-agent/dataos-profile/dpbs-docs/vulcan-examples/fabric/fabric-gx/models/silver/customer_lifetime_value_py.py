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
    description="Customer lifetime value aggregation using Python and pandas.",
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
                SUM(oi.quantity * oi.unit_price),
                0
            ) AS total_spend

        FROM {customers} AS c

        LEFT JOIN {regions} AS r
            ON c.region_id = r.region_id

        LEFT JOIN {orders} AS o
            ON c.customer_id = o.customer_id

        LEFT JOIN {order_items} AS oi
            ON o.order_id = oi.order_id

        GROUP BY
            c.customer_id,
            c.name,
            r.region_name
    """

    df = context.fetchdf(query)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "customer_id",
                "customer_name",
                "region_name",
                "total_orders",
                "total_items",
                "total_spend",
            ]
        )

    df.columns = df.columns.str.lower()

    df["total_orders"] = pd.to_numeric(
        df["total_orders"],
        errors="coerce",
    ).fillna(0).astype("int64")

    df["total_items"] = pd.to_numeric(
        df["total_items"],
        errors="coerce",
    ).fillna(0).astype("int64")

    df["total_spend"] = pd.to_numeric(
        df["total_spend"],
        errors="coerce",
    ).fillna(0)

    return df[
        [
            "customer_id",
            "customer_name",
            "region_name",
            "total_orders",
            "total_items",
            "total_spend",
        ]
    ]