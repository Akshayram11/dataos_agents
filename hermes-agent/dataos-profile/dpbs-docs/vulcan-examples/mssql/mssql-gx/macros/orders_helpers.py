"""Reusable SQL macros for orders analytics models."""

from __future__ import annotations

from vulcan import SQL, macro


@macro()
def safe_ratio(evaluator, numerator: SQL, denominator: SQL, scale: int = 4) -> str:
    """Return a rounded ratio, defaulting to 0 when the denominator is zero."""
    return f"ROUND(COALESCE(CAST({numerator} AS DECIMAL(18, 4)) / NULLIF({denominator}, 0), 0), {scale})"


@macro()
def revenue_order_filter(evaluator, status_column: SQL) -> str:
    """Return the standard revenue-bearing order filter."""
    return f"{status_column} <> 'Cancelled'"
