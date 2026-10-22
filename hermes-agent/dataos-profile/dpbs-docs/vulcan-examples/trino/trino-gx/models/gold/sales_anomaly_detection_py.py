from vulcan import ExecutionContext, model
from vulcan import ModelKindName
import pandas as pd


@model(
    "gold_sparkv.sales_anomaly_detection_py",
    columns={
        "order_date": "date",
        "region_id": "string",
        "category": "string",
        "daily_revenue": "decimal(18,2)",
        "rolling_7d_revenue": "decimal(18,2)",
        "revenue_difference": "decimal(18,2)",
        "is_anomaly": "boolean",
    },
    kind=dict(name=ModelKindName.FULL),
    grains=[
        "order_date",
        "region_id",
        "category",
    ],
    depends_on=[
        "silverv2.fct_daily_sales",
    ],
    tags=["gold", "python", "analytics"],
    description="Simple seven-day rolling revenue anomaly detection.",
)
def execute(
    context: ExecutionContext,
    start,
    end,
    execution_time,
    **kwargs,
) -> pd.DataFrame:

    daily_sales = context.resolve_table(
        "silverv2.fct_daily_sales"
    )

    query = f"""
        WITH daily_revenue AS (
            SELECT
                order_date,
                region_id,
                category,

                CAST(
                    SUM(total_revenue)
                    AS DECIMAL(18,2)
                ) AS daily_revenue

            FROM {daily_sales}

            GROUP BY
                order_date,
                region_id,
                category
        ),

        calculated AS (
            SELECT
                order_date,
                region_id,
                category,
                daily_revenue,

                CAST(
                    AVG(daily_revenue) OVER (
                        PARTITION BY
                            region_id,
                            category
                        ORDER BY
                            order_date
                        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                    )
                    AS DECIMAL(18,2)
                ) AS rolling_7d_revenue

            FROM daily_revenue
        )

        SELECT
            order_date,
            region_id,
            category,
            daily_revenue,
            rolling_7d_revenue,

            CAST(
                daily_revenue - rolling_7d_revenue
                AS DECIMAL(18,2)
            ) AS revenue_difference,

            CAST(
                daily_revenue >
                rolling_7d_revenue * 1.5
                AS BOOLEAN
            ) AS is_anomaly

        FROM calculated
    """

    return context.engine_adapter.fetchdf(query)