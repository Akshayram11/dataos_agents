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
    tags=["gold", "python"],
    description="Simple sales anomaly detection using a seven-day rolling average.",
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

    df = context.fetchdf(query)

    if df.empty:
        return pd.DataFrame(
            columns=[
                "order_date",
                "region_id",
                "category",
                "daily_revenue",
                "rolling_7d_revenue",
                "is_anomaly",
            ]
        )

    df.columns = df.columns.str.lower()

    df["daily_revenue"] = pd.to_numeric(
        df["daily_revenue"],
        errors="coerce",
    )

    df["rolling_7d_revenue"] = (
        df
        .sort_values(
            ["region_id", "category", "order_date"]
        )
        .groupby(
            ["region_id", "category"]
        )["daily_revenue"]
        .transform(
            lambda x: x.rolling(
                window=7,
                min_periods=1,
            ).mean()
        )
    )

    df["is_anomaly"] = (
        df["daily_revenue"]
        > df["rolling_7d_revenue"] * 1.5
    )

    return df[
        [
            "order_date",
            "region_id",
            "category",
            "daily_revenue",
            "rolling_7d_revenue",
            "is_anomaly",
        ]
    ]