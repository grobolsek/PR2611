"""Forecast total crime trends from 2000 onwards.

Aggregates all rows across pure annual CSV files located in data/by_year,
cleans month formatting, and fits a Holt-Winters model to project
total expected crime counts into upcoming years.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def load_all_data_from_2000(by_year_dir: Path) -> pd.Series:
    """Find annual files in data/by_year, count total crime, and merge months."""
    # Find files that have exactly 4 digits in their name (e.g., 2000.csv, 2024.csv)
    all_files = sorted(
        [f for f in by_year_dir.glob("*.csv") if re.match(r"^\d{4}$", f.stem)],
    )

    if not all_files:
        raise FileNotFoundError(f"No annual files (e.g., 2000.csv) found in directory: {by_year_dir}")

    combined_records = []

    for file_path in all_files:
        file_year = int(file_path.stem)

        # Restrict the range strictly from year 2000 to 2024
        if file_year < 2000 or file_year > 2023:
            continue

        logger.info(f"Loading data for the year {file_year}...")

        df = pd.read_csv(file_path, encoding="utf-8", quoting=1, low_memory=False)

        if df.empty:
            continue

        # Determine which month column exists in this specific file
        month_col = "MesecStoritve" if "MesecStoritve" in df.columns else "Mesec"
        if month_col not in df.columns:
            logger.warning(f"File {file_path.name} is missing a month column. Skipping.")
            continue

        # Aggregate - count the number of rows per month
        df_monthly = df.groupby(month_col).size().reset_index(name="total_crime")

        # Clean the month format (remove potential trailing .0)
        df_monthly[month_col] = df_monthly[month_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

        # Construct the full date string "MM.YYYY"
        df_monthly["Date_Str"] = df_monthly[month_col].apply(
            lambda x: f"{x.zfill(2)}.{file_year}" if "." not in x else x,
        )

        combined_records.append(df_monthly[["Date_Str", "total_crime"]])

    if not combined_records:
        raise ValueError("None of the files found in data/by_year contain valid data.")

    # Merge all years into a single continuous time series
    df_all = pd.concat(combined_records, ignore_index=True)
    df_all["Datum"] = pd.to_datetime(df_all["Date_Str"], format="%m.%Y")
    df_all = df_all.sort_values("Datum").set_index("Datum")

    # Resample to monthly frequency (Monthly Start)
    series = df_all.groupby("Datum")["total_crime"].sum().asfreq("MS")

    # Handle missing data or anomalies using linear interpolation instead of dropping to 0
    series = series.replace(0, np.nan)
    series = series.interpolate(method="linear")
    return series


def main() -> None:
    base_dir = Path(__file__).parents[2]

    # Path configuration pointing directly to data/by_year
    by_year_dir = base_dir / "data" / "by_year"

    try:
        # 1. Load data from year 2000 onwards from the correct folder
        ts_data = load_all_data_from_2000(by_year_dir)

        logger.info(
            f"Time series successfully built: from {ts_data.index.min().strftime('%m.%Y')} to {ts_data.index.max().strftime('%m.%Y')}.",
        )

        # 2. Fit Holt-Winters model on the entire historical period
        logger.info("Training Holt-Winters model...")
        model = ExponentialSmoothing(
            ts_data,
            trend="add",
            seasonal="add",
            seasonal_periods=12,
        ).fit()

        # Forecast the next 24 months (2 years) for a better visualization
        prihodnost = model.forecast(24)

        print("\n========================================================")
        print("STATICTIC PREDICTION:")
        print("========================================================")
        for datum, vrednost in prihodnost.head(12).items():
            print(f"{datum.strftime('%m.%Y')}: Estimated total crime count = {max(0, int(round(vrednost)))}")

        # 3. Plot the chart
        plt.figure(figsize=(14, 7))
        plt.plot(ts_data.index, ts_data.values, label="Historical Crime Data (2000+)", color="royalblue", alpha=0.8)
        plt.plot(prihodnost.index, prihodnost.values, label="Holt-Winters Future Forecast", color="crimson", linestyle="--", linewidth=2)

        plt.title("Long-term Trend and Forecast of Total Crime in Slovenia (From 2000 Onwards)", fontsize=14, pad=15)
        plt.xlabel("Year", fontsize=12)
        plt.ylabel("Monthly Count of All Criminal Offences", fontsize=12)
        plt.legend(fontsize=11, loc="upper right")
        plt.grid(True, linestyle=":", alpha=0.6)

        # Save the generated chart into the analysis directory
        plot_out = base_dir / "data" / "analysis" / "crime_forecast.png"
        plot_out.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(plot_out, dpi=300, bbox_inches="tight")
        logger.info(f"Forecast chart successfully saved to: {plot_out}")

    except Exception as e:
        logger.error(f"An error occurred during analysis: {e}")


if __name__ == "__main__":
    main()
