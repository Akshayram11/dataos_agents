"""
Python FULL model: Sales Anomaly Detection.

Calculates rolling revenue metrics and identifies unusually
high or low revenue days for each region and product category.
"""

import typing as t
from datetime import datetime

import pandas as pd

from vulcan import ExecutionContext, ModelKindName, model


@model(
    "s3lhdepotrr.gold_sparkv.sales_anomaly_detection_py",
    columns={
        "order_date": "timestamp",
        "region_id": "int",
        "region_name": "text",
        "category": "text",
        "total_revenue": "double",
        "rolling_7d_revenue": "double",
        "avg_7d_revenue": "double",
        "revenue_deviation": "double",
        "anomaly_status": "text",
    },
    kind=dict(name=ModelKindName.FULL),
    grains=[
        "order_date",
        "region_id",
        "category",
    ],
    depends_on=[
        "s3lhdepotrr.silver_sparkv.fct_daily_sales",
    ],
    tags=[
        "gold",
        "sales",
        "python",
        "analytics",
        "anomaly",
    ],
    description=(
        "Sales anomaly detection using rolling seven-day "
        "revenue statistics calculated in Python."
    ),
)
def execute(
    context: ExecutionContext,
    start: datetime,
    end: datetime,
    execution_time: datetime,
    **kwargs: t.Any,
) -> pd.DataFrame:

    # ---------------------------------------------------------
    # Resolve dependency
    # ---------------------------------------------------------

    daily_sales = context.resolve_table(
        "s3lhdepotrr.silver_sparkv.fct_daily_sales"
    )

    # ---------------------------------------------------------
    # Fetch source data
    # ---------------------------------------------------------

    query = f"""
        SELECT
            order_date,
            region_id,
            region_name,
            category,
            total_revenue
        FROM {daily_sales}
        ORDER BY
            region_id,
            category,
            order_date
    """

    df = context.fetchdf(query)

    if df.empty:
        yield from ()
        return

    # ---------------------------------------------------------
    # Normalize column names
    # ---------------------------------------------------------

    df.columns = df.columns.str.lower()

    # ---------------------------------------------------------
    # Make sure date is a pandas datetime
    # ---------------------------------------------------------

    df["order_date"] = pd.to_datetime(
        df["order_date"]
    )

    df["total_revenue"] = (
        pd.to_numeric(
            df["total_revenue"],
            errors="coerce",
        )
        .fillna(0.0)
    )

    # ---------------------------------------------------------
    # Calculate rolling 7-day metrics
    #
    # Each region/category combination has its own
    # independent rolling window.
    # ---------------------------------------------------------

    df = df.sort_values(
        [
            "region_id",
            "category",
            "order_date",
        ]
    )

    grouped = df.groupby(
        [
            "region_id",
            "category",
        ],
        group_keys=False,
    )

    df["rolling_7d_revenue"] = grouped[
        "total_revenue"
    ].transform(
        lambda x: x.rolling(
            window=7,
            min_periods=1,
        ).sum()
    )

    df["avg_7d_revenue"] = grouped[
        "total_revenue"
    ].transform(
        lambda x: x.rolling(
            window=7,
            min_periods=1,
        ).mean()
    )

    # ---------------------------------------------------------
    # Revenue deviation
    #
    # Measures the percentage difference between the
    # current revenue and rolling seven-day average.
    # ---------------------------------------------------------

    df["revenue_deviation"] = (
        (
            df["total_revenue"]
            - df["avg_7d_revenue"]
        )
        / df["avg_7d_revenue"].replace(0, pd.NA)
    ).fillna(0.0)

    # ---------------------------------------------------------
    # Anomaly classification
    # ---------------------------------------------------------

    df["anomaly_status"] = "NORMAL"

    df.loc[
        df["revenue_deviation"] >= 0.50,
        "anomaly_status",
    ] = "HIGH"

    df.loc[
        df["revenue_deviation"] <= -0.50,
        "anomaly_status",
    ] = "LOW"

    # ---------------------------------------------------------
    # Final output
    # ---------------------------------------------------------

    yield df[
        [
            "order_date",
            "region_id",
            "region_name",
            "category",
            "total_revenue",
            "rolling_7d_revenue",
            "avg_7d_revenue",
            "revenue_deviation",
            "anomaly_status",
        ]
    ]