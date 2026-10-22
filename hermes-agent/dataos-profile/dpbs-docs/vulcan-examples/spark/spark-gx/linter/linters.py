"""Custom linter rules for the orders-analytics data product.

These rules keep the demo aligned with the project contract:
generated bronze sources, explicit grains, owners, and quality coverage.
"""

import typing as t

from vulcan import Model, Rule, RuleViolation


def _has_any(model: Model, *attribute_names: str) -> bool:
    for attribute_name in attribute_names:
        value = getattr(model, attribute_name, None)
        if value:
            return True
    return False


def _model_name(model: Model) -> str:
    return str(getattr(model, "name", ""))


LAKEHOUSE_CATALOG = "s3lhdepotrr"
BRONZE_SCHEMA = f"{LAKEHOUSE_CATALOG}.bronze_sparkv"
SILVER_SCHEMA = f"{LAKEHOUSE_CATALOG}.silver_sparkv"
GOLD_SCHEMA = f"{LAKEHOUSE_CATALOG}.gold_sparkv"


def _is_sql_data_model(model: Model) -> bool:
    model_name = _model_name(model)
    return model_name.startswith(
        (f"{BRONZE_SCHEMA}.", f"{SILVER_SCHEMA}.", f"{GOLD_SCHEMA}.")
    )


class RequireGrainForAllModels(Rule):
    """Require every model to declare a grain."""

    def check_model(self, model: Model) -> t.Optional[RuleViolation]:
        if not _is_sql_data_model(model):
            return None
        if not _has_any(model, "grain", "grains"):
            return self.violation(
                "\nAll orders-analytics models must define `grains` so semantic joins and DQ checks have a clear row-level contract.\n"
            )
        return None


class RequireOwnerForAllModels(Rule):
    """Require model ownership metadata."""

    def check_model(self, model: Model) -> t.Optional[RuleViolation]:
        if not _is_sql_data_model(model):
            return None
        if not getattr(model, "owner", None):
            return self.violation("\nAll orders-analytics models must define an owner.\n")
        return None


class RequireAssertionsOrAuditsForAllModels(Rule):
    """Require built-in assertions or custom audits on every model."""

    def check_model(self, model: Model) -> t.Optional[RuleViolation]:
        if not _is_sql_data_model(model):
            return None
        if _has_any(model, "assertions", "audits"):
            return None
        return self.violation(
            "\nModels should include assertions or custom audits for completeness, validity, or uniqueness.\n"
        )


class RequireDqForAnalyticsModels(Rule):
    """Require DQ suites for silver and gold analytical models."""

    def check_model(self, model: Model) -> t.Optional[RuleViolation]:
        model_name = _model_name(model)
        if not (
            model_name.startswith(f"{SILVER_SCHEMA}.")
            or model_name.startswith(f"{GOLD_SCHEMA}.")
        ):
            return None

        check_suites = getattr(getattr(self, "context", None), "check_suites", {}) or {}
        for suite in check_suites.values():
            suite_model_name = str(getattr(suite, "model_name", ""))
            if suite_model_name == model_name or suite_model_name.endswith(f".{model_name}"):
                return None

        return self.violation(
            "\nSilver and gold models should have a matching DQ suite under `models/dq`.\n"
        )


class RequireGeneratedBronzeSources(Rule):
    """Require bronze source models to read from generated external tables."""

    def check_model(self, model: Model) -> t.Optional[RuleViolation]:
        model_name = _model_name(model)
        if not model_name.startswith(f"{BRONZE_SCHEMA}."):
            return None

        query = str(getattr(model, "query", "") or "").lower()
        if model_name == f"{BRONZE_SCHEMA}.order_status_lookup":
            return None
        if f"{LAKEHOUSE_CATALOG}.public." not in query or "_ext" not in query:
            return self.violation(
                "\nBronze generated source models should read from `s3lhdepotrr.public.*_ext` Iceberg tables seeded in `before_all`.\n"
            )
        return None
