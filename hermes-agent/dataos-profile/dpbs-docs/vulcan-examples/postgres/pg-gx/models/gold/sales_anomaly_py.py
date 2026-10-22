import typing as t
from datetime import datetime

import pandas as pd

from vulcan import ExecutionContext, model
from vulcan import ModelKindName


@model(
    "goldv1.sales_anomaly_detection_py",
    columns={
        "order_date": "date",
        "region_name": "text",
        "daily_revenue": "double",
        "rolling_7d_average": "double",
        "rolling_7d_stddev": "double",
        "revenue_deviation": "double",
        "anomaly_score": "double",
        "anomaly_status": "text",
    },
    kind=dict(
        name=ModelKindName.FULL,
    ),
    grains=["order_date", "region_name"],
    depends_on=[
        "silverv1.fct_daily_sales",
    ],
    tags=["gold", "sales", "python", "anomaly-detection"],
    description="Detects unusual daily sales using rolling statistical analysis.",
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
            CAST(order_date AS DATE) AS order_date,
            region_name,
            SUM(total_revenue) AS daily_revenue
        FROM {daily_sales}
        GROUP BY
            CAST(order_date AS DATE),
            region_name
        ORDER BY
            region_name,
            order_date
    """

    df = context.fetchdf(query)

    df["daily_revenue"] = df["daily_revenue"].fillna(0)

    # Calculate rolling statistics separately for every region
    df["rolling_7d_average"] = (
        df.groupby("region_name")["daily_revenue"]
        .transform(
            lambda x: x.rolling(
                window=7,
                min_periods=3,
            ).mean()
        )
    )

    df["rolling_7d_stddev"] = (
        df.groupby("region_name")["daily_revenue"]
        .transform(
            lambda x: x.rolling(
                window=7,
                min_periods=3,
            ).std()
        )
    )

    df["rolling_7d_stddev"] = (
        df["rolling_7d_stddev"]
        .fillna(0)
    )

    # Difference from expected revenue
    df["revenue_deviation"] = (
        df["daily_revenue"]
        - df["rolling_7d_average"]
    )

    # Z-score style anomaly score
    df["anomaly_score"] = (
        df["revenue_deviation"]
        / df["rolling_7d_stddev"].replace(0, 1)
    )

    def classify_anomaly(score):
        if score >= 2:
            return "HIGH_REVENUE_ANOMALY"
        elif score <= -2:
            return "LOW_REVENUE_ANOMALY"
        else:
            return "NORMAL"

    df["anomaly_status"] = (
        df["anomaly_score"]
        .apply(classify_anomaly)
    )

    return df[
        [
            "order_date",
            "region_name",
            "daily_revenue",
            "rolling_7d_average",
            "rolling_7d_stddev",
            "revenue_deviation",
            "anomaly_score",
            "anomaly_status",
        ]
    ]