"""Exploratory analysis helpers for formatted crime-statistics DataFrames.

Provides functions for inspecting, validating, and auditing DataFrames that
have already been processed by the formatting pipeline
(:mod:`formatting.formatter`).  These functions are intended for interactive
use and reporting rather than for the production pipeline.
"""

import logging
import re

import pandas as pd

from formatting.formatting_functions import _COLUMN_PATTERNS, CRIME_CLUSTERS

logger = logging.getLogger(__name__)


def unique_values(
    data: pd.DataFrame,
    *,
    exclude: list[str | int] | None = None,
) -> dict[str, list]:
    """Return and log unique non-null values for each column.

    Args:
        data: Input DataFrame.
        exclude: Column names or integer positions to skip. Defaults to ``None``.
    """
    excluded = set()
    for item in exclude or []:
        if isinstance(item, int):
            excluded.add(data.columns[item])
        else:
            excluded.add(item)

    def _sort(series: pd.Series) -> list:
        vals = series.dropna().unique()
        if isinstance(series.dtype, pd.CategoricalDtype) and series.dtype.ordered:
            cats = list(series.cat.categories)
            return sorted(vals.tolist(), key=cats.index)
        return sorted(vals.tolist())

    result = {col: _sort(data[col]) for col in data.columns if col not in excluded}
    for col, vals in result.items():
        logger.info("%s: %s", col, vals)
    return result


def validate_formats(
    data: pd.DataFrame,
    patterns: dict[str, str] | None = None,
) -> dict[str, list]:
    """Check columns against expected regex patterns and report invalid values.

    Args:
        data: Input DataFrame.
        patterns: Dict of column → full-match regex. Defaults to ``_COLUMN_PATTERNS``.

    Returns:
        Dict mapping column name to a list of (row_index, value) tuples that
        failed validation. Columns with no violations are omitted.
    """
    if patterns is None:
        patterns = _COLUMN_PATTERNS

    violations: dict[str, list] = {}
    for col, pattern in patterns.items():
        if col not in data.columns:
            logger.warning("validate_formats: column %r not found in DataFrame", col)
            continue
        compiled = re.compile(r"^(?:" + pattern + r")$")
        bad = [(idx, val) for idx, val in data[col].dropna().items() if not compiled.match(str(val))]
        if bad:
            violations[col] = bad
            logger.warning(
                "validate_formats: %d invalid value(s) in %r: %s",
                len(bad),
                col,
                bad[:5],
            )
        else:
            logger.info("validate_formats: %r OK", col)

    return violations


def check_unmapped(df: pd.DataFrame, crime_col: str) -> list[str]:
    """Return crime descriptions in *crime_col* that are absent from :data:`CRIME_CLUSTERS`.

    Args:
        df: Input DataFrame.
        crime_col: Column containing crime description strings.

    Returns:
        Sorted list of unmapped crime description strings.
    """
    known = {crime for crimes in CRIME_CLUSTERS.values() for crime in crimes}
    return sorted(df[crime_col].dropna().unique()[~pd.Index(df[crime_col].dropna().unique()).isin(known)].tolist())
