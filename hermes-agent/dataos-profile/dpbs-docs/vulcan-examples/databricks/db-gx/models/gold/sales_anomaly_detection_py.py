import typing as t
from datetime import datetime

import pandas as pd

from vulcan import ExecutionContext, model
from vulcan import ModelKindName


@model(
    "goldv1.sales_anomaly_detection_py",
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
        "silverv1.fct_daily_sales",
    ],
    tags=["gold", "python", "analytics"],
    description="Simple seven-day rolling revenue anomaly detection.",
)
def execute(
    context: ExecutionContext,
    start: datetime,
    end: datetime,
    execution_time: datetime,
    **kwargs: t.Any,
) -> pd.DataFrame:

    daily_sales = context.resolve_table(
        "silverv1.fct_daily_sales"
    )

    query = f"""
        SELECT
            order_date,
            region_id,
            category,
            SUM(total_revenue) AS daily_revenue
        FROM {daily_sales}
        GROUP BY
            order_date,
            region_id,
            category
        ORDER BY
            region_id,
            category,
            order_date
    """

    result = context.fetchdf(query)

    result["order_date"] = pd.to_datetime(
        result["order_date"]
    )

    result["daily_revenue"] = pd.to_numeric(
        result["daily_revenue"]
    )

    result["rolling_7d_revenue"] = (
        result
        .groupby(["region_id", "category"])["daily_revenue"]
        .transform(
            lambda x: x.rolling(
                window=7,
                min_periods=1,
            ).mean()
        )
    )

    result["revenue_difference"] = (
        result["daily_revenue"]
        - result["rolling_7d_revenue"]
    )

    result["is_anomaly"] = (
        result["daily_revenue"]
        > result["rolling_7d_revenue"] * 1.5
    )

    result["daily_revenue"] = result["daily_revenue"].round(2)
    result["rolling_7d_revenue"] = (
        result["rolling_7d_revenue"].round(2)
    )
    result["revenue_difference"] = (
        result["revenue_difference"].round(2)
    )

    return result[
        [
            "order_date",
            "region_id",
            "category",
            "daily_revenue",
            "rolling_7d_revenue",
            "revenue_difference",
            "is_anomaly",
        ]
    ]