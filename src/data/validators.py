"""
Schema and data quality validators for inference snapshots.
Raises descriptive errors so Airflow tasks fail with actionable messages.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SchemaSpec:
    """
    Minimal schema specification for an inference snapshot.

    Attributes:
        required_columns:   Columns that must be present.
        numeric_columns:    Columns expected to hold numeric values.
        nullable_columns:   Columns that are allowed to contain NaN.
        max_null_rate:      Maximum tolerated null-rate for non-nullable columns (0-1).
        min_rows:           Minimum acceptable row count.
    """

    required_columns: list[str] = field(default_factory=list)
    numeric_columns: list[str] = field(default_factory=list)
    nullable_columns: list[str] = field(default_factory=list)
    max_null_rate: float = 0.05
    min_rows: int = 1


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [f"Validation {'PASSED' if self.passed else 'FAILED'}"]
        for e in self.errors:
            lines.append(f"  [ERROR]   {e}")
        for w in self.warnings:
            lines.append(f"  [WARNING] {w}")
        return "\n".join(lines)


def validate_schema(df: pd.DataFrame, spec: SchemaSpec) -> ValidationResult:
    """
    Validate a DataFrame against a SchemaSpec.

    Args:
        df:   Inference snapshot DataFrame.
        spec: Expected schema.

    Returns:
        ValidationResult – call .passed to branch in Airflow.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Row count check
    if len(df) < spec.min_rows:
        errors.append(
            f"Snapshot has {len(df)} rows; minimum required is {spec.min_rows}."
        )

    # Required column presence
    missing_cols = [c for c in spec.required_columns if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")

    # Numeric type checks
    for col in spec.numeric_columns:
        if col not in df.columns:
            continue  # already caught above
        if not pd.api.types.is_numeric_dtype(df[col]):
            errors.append(
                f"Column '{col}' is expected to be numeric but has dtype '{df[col].dtype}'."
            )

    # Null-rate checks
    for col in df.columns:
        null_rate = df[col].isna().mean()
        if col in spec.nullable_columns:
            if null_rate > 0.5:
                warnings.append(
                    f"Nullable column '{col}' has a high null rate: {null_rate:.1%}."
                )
        else:
            if null_rate > spec.max_null_rate:
                errors.append(
                    f"Column '{col}' null rate {null_rate:.1%} exceeds threshold {spec.max_null_rate:.1%}."
                )

    passed = len(errors) == 0
    result = ValidationResult(passed=passed, errors=errors, warnings=warnings)
    log_fn = logger.info if passed else logger.error
    log_fn("%s", result)
    return result


def assert_valid(df: pd.DataFrame, spec: SchemaSpec) -> None:
    """
    Validate and raise ValueError if validation fails.
    Suitable for use inside Airflow PythonOperator callables.
    """
    result = validate_schema(df, spec)
    if not result.passed:
        raise ValueError(
            f"Inference snapshot validation failed:\n{result}"
        )


def coerce_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Attempt to coerce listed columns to numeric, setting non-parseable values to NaN.
    Returns a copy of the DataFrame.
    """
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_default_spec(df: pd.DataFrame) -> SchemaSpec:
    """
    Auto-generate a permissive SchemaSpec from a sample DataFrame.
    Useful for bootstrapping when no spec is defined yet.
    """
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    return SchemaSpec(
        required_columns=df.columns.tolist(),
        numeric_columns=numeric_cols,
        nullable_columns=[],
        max_null_rate=0.1,
        min_rows=10,
    )