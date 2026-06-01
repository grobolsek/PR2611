"""Correlate specific crime types with monthly weather data for any given year.

Provides functions to aggregate crime data by month and region, merge it with
weather metrics (temperature, precipitation), and calculate Pearson correlation
coefficients for specific analytical crime clusters.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

def _normalize_location(location: object) -> object:
    """Ensure location strings are stripped and uniform."""
    if pd.isna(location):
        return location
    text = str(location).strip()
    if text.upper() == "GPU":
        return "NI PODATKA"
    return text


def get_crime_weather_data(
    crimes: pd.DataFrame,
    weather: pd.DataFrame,
    crime_cluster: str,
    city_col: str = "PUStoritveKD",
    month_col: str = "MesecStoritve",
) -> pd.DataFrame:
    """Filter crimes by a specific cluster, aggregate by month/region, and merge with weather."""
    df_crimes = crimes.copy()
    df_weather = weather.copy()

    df_crimes[city_col] = df_crimes[city_col].apply(_normalize_location)
    df_weather[city_col] = df_weather[city_col].apply(_normalize_location)

    if "KD_SKUPINA" not in df_crimes.columns:
        raise KeyError("Column 'KD_SKUPINA' missing in crimes DataFrame.")
        
    filtered_crimes = df_crimes[df_crimes["KD_SKUPINA"] == crime_cluster]
    
    if filtered_crimes.empty:
        logger.warning("No rows found for crime cluster %r", crime_cluster)
        return pd.DataFrame()

    crime_counts = (
        filtered_crimes.groupby([month_col, city_col], dropna=False)
        .size()
        .reset_index(name="stevilka_zlocinov")
    )

    crime_counts[month_col] = crime_counts[month_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    df_weather[month_col] = df_weather[month_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    merged = pd.merge(crime_counts, df_weather, on=[month_col, city_col], how="inner")
    
    return merged


def compute_correlation(
    merged_data: pd.DataFrame, 
    metrics: list[str] | None = None
) -> pd.DataFrame:
    """Calculate the Pearson correlation matrix between crime counts and weather metrics."""
    if merged_data.empty:
        return pd.DataFrame()
        
    if metrics is None:
        metrics = ["povprecna_temp", "kolicina_padavin_mm"]

    columns_to_correlate = ["stevilka_zlocinov"] + metrics
    available_cols = [c for c in columns_to_correlate if c in merged_data.columns]
    
    return merged_data[available_cols].corr()


def run_weather_correlation_analysis(year: int, base_directory: Path) -> None:
    """Load data and run correlation analysis for a specific year.
    
    Args:
        year: The year to analyze (e.g., 2023, 2024).
        base_directory: Root directory of the project.
    """
    # Dynamic file paths based on the selected year
    formatted_file = base_directory / "data" / "formatted" / f"kd{year}.csv"
    weather_file = base_directory / "data" / "weather" / f"slovenia_weather_{year}.csv"
    
    # Check if files exist
    if not formatted_file.exists():
        logger.error(f"Cleaned crime data for the year {year} does not exist: {formatted_file}")
        return
    if not weather_file.exists():
        logger.error(f"Weather data for the year {year} does not exist: {weather_file}")
        return

    logger.info(f"Loading data and starting the analysis for the year {year}...")
    
    df_crimes = pd.read_csv(formatted_file, encoding="utf-8", quoting=1, low_memory=False)
    df_weather = pd.read_csv(weather_file, encoding="utf-8")
    
    # 1. Analysis for Nasilje nad osebami
    cluster_nasilje = "Nasilje nad osebami"
    merged_nasilje = get_crime_weather_data(df_crimes, df_weather, crime_cluster=cluster_nasilje)
    corr_nasilje = compute_correlation(merged_nasilje)
    
    print(f"\n=== CORRELATION MATRIX FOR: {cluster_nasilje} ({year}) ===")
    print(corr_nasilje)
    
    # 2. Analysis for Premoženjska kazniva dejanja
    cluster_premozenje = "Premoženjska kazniva dejanja"
    merged_premozenje = get_crime_weather_data(df_crimes, df_weather, crime_cluster=cluster_premozenje)
    corr_premozenje = compute_correlation(merged_premozenje)
    
    print(f"\n=== CORRELATION MATRIX FOR: {cluster_premozenje} ({year}) ===")
    print(corr_premozenje)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    
    # Find the root directory of the project
    base_dir = Path(__file__).parents[2]
    
    # --- CHANGE THE YEAR HERE ---
    IZBRANO_LETO = 2024
    # --------------------------------------
    
    run_weather_correlation_analysis(year=IZBRANO_LETO, base_directory=base_dir)