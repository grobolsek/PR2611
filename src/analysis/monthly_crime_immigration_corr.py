"""Correlate monthly crime counts with monthly issued immigration permits.

Loads the aggregated monthly immigration CSV and matches it against monthly
crime counts for a specific year to compute Pearson correlation coefficients.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_monthly_crime_counts(df_crimes: pd.DataFrame, crime_cluster: str) -> pd.DataFrame:
    """Filter crime by cluster and return the monthly count of criminal offenses."""
    if "KD_SKUPINA" not in df_crimes.columns:
        raise KeyError("The column 'KD_SKUPINA' is missing from the crime database.")

    df_filtered = df_crimes[df_crimes["KD_SKUPINA"] == crime_cluster].copy()

    if df_filtered.empty:
        logger.warning(f"No rows found for the specified crime cluster: {crime_cluster}")
        return pd.DataFrame()

    # Aggregate data to a monthly level
    crime_monthly = df_filtered.groupby("MesecStoritve").size().reset_index(name="crime_count")

    # Clean the string format (remove potential trailing .0)
    crime_monthly["MesecStoritve"] = crime_monthly["MesecStoritve"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    return crime_monthly


def analyze_monthly_correlation(year: int, base_directory: Path, crime_cluster: str) -> pd.DataFrame:
    """Merge monthly crime and immigration data to calculate the Pearson correlation."""
    # File paths configuration
    crime_file = base_directory / "data" / "formatted" / f"kd{year}.csv"
    immigration_file = base_directory / "data" / "immigration" / "monthly_immigration_trends.csv"

    if not crime_file.exists():
        logger.error(f"Crime data file for the year {year} does not exist: {crime_file}")
        return pd.DataFrame()
    if not immigration_file.exists():
        logger.error(f"Monthly immigration file does not exist: {immigration_file}")
        return pd.DataFrame()

    # Data ingestion
    df_crimes = pd.read_csv(crime_file, encoding="utf-8", quoting=1, low_memory=False)
    df_immigration = pd.read_csv(immigration_file, encoding="utf-8")

    # Extract monthly crime totals
    df_crime_monthly = get_monthly_crime_counts(df_crimes, crime_cluster)

    if df_crime_monthly.empty:
        return pd.DataFrame()

    # --- DATA CLEANING: Unify data types for the join key 'MesecStoritve' ---
    # Convert to string, strip whitespaces, and remove decimal parts if present
    df_crime_monthly["MesecStoritve"] = df_crime_monthly["MesecStoritve"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    df_immigration["MesecStoritve"] = df_immigration["MesecStoritve"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    # Ensure standard length formatting (e.g., transform '1.2025' into '01.2025' if needed)
    df_crime_monthly["MesecStoritve"] = df_crime_monthly["MesecStoritve"].apply(lambda x: f"0{x}" if len(x) == 6 else x)
    df_immigration["MesecStoritve"] = df_immigration["MesecStoritve"].apply(lambda x: f"0{x}" if len(x) == 6 else x)
    # -------------------------------------------------------------------------

    # Merge datasets using an inner join on the month identifier
    df_merged = pd.merge(df_crime_monthly, df_immigration, on="MesecStoritve", how="inner")

    if df_merged.empty:
        logger.warning(f"No matching temporal data between crime and immigration for the year {year}. Check date values.")
        return pd.DataFrame()

    # Compute correlation matrix between crime counts and monthly issued permits
    columns_to_correlate = ["crime_count", "Izdana_Dovoljenja_Mesec"]
    return df_merged[columns_to_correlate].corr()


if __name__ == "__main__":
    base_dir = Path(__file__).parents[2]

    SELECTED_YEAR = 2021  # Adjust according to available annual datasets

    print(f"\n--- MONTHLY CORRELATION ANALYSIS FOR THE YEAR {SELECTED_YEAR} ---")

    # 1. Analyze Property Crimes (Premoženjska kazniva dejanja)
    cluster_property = "Premoženjska kazniva dejanja"
    corr_property = analyze_monthly_correlation(SELECTED_YEAR, base_dir, cluster_property)
    if not corr_property.empty:
        print(f"\n=== MONTHLY CORRELATION: {cluster_property} ===")
        print(corr_property)

    # 2. Analyze Crimes Against Persons / Violence (Nasilje nad osebami)
    cluster_violence = "Nasilje nad osebami"
    corr_violence = analyze_monthly_correlation(SELECTED_YEAR, base_dir, cluster_violence)
    if not corr_violence.empty:
        print(f"\n=== MONTHLY CORRELATION: {cluster_violence} ===")
        print(corr_violence)
