from vulcan import ExecutionContext, model
from vulcan import ModelKindName
import pandas as pd


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
        "bronzev2.customers",
        "bronzev2.orders",
        "bronzev2.order_items",
        "bronzev2.regions",
    ],
    tags=["silver", "python"],
    description="Simple customer lifetime value model.",
)
def execute(
    context: ExecutionContext,
    start,
    end,
    execution_time,
    **kwargs,
) -> pd.DataFrame:

    customers = context.resolve_table("bronzev2.customers")
    orders = context.resolve_table("bronzev2.orders")
    order_items = context.resolve_table("bronzev2.order_items")
    regions = context.resolve_table("bronzev2.regions")

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

            CAST(
                COALESCE(
                    SUM(oi.quantity * oi.unit_price),
                    0
                )
                AS DECIMAL(18,2)
            ) AS total_spend,

            CAST(
                CASE
                    WHEN COUNT(DISTINCT o.order_id) > 0
                    THEN
                        COALESCE(
                            SUM(oi.quantity * oi.unit_price),
                            0
                        )
                        / COUNT(DISTINCT o.order_id)
                    ELSE 0
                END
                AS DECIMAL(18,2)
            ) AS average_order_value

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

    result = context.engine_adapter.fetchdf(query)

    result["customer_lifetime_value"] = (
        result["average_order_value"]
    )

    return result
