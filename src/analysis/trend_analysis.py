"""Analyze historical crime trends in Slovenia across multiple years.

Loads all available formatted annual CSV files, aggregates crime counts
by year and crime cluster, and uncovers long-term structural shifts.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def load_all_years(formatted_dir: Path) -> pd.DataFrame:
    """Find and combine all annual formatted crime CSV files into one DataFrame."""
    files = sorted(formatted_dir.glob("kd20*.csv"))
    if not files:
        logger.error(f"No kd20XX.csv files found in directory: {formatted_dir}!")
        return pd.DataFrame()
        
    all_dfs = []
    for f in files:
        # Extract the year from the filename (e.g., 'kd2024.csv' -> 2024)
        year = int(f.stem[2:])
        logger.info(f"Loading data for year {year}...")
        
        df = pd.read_csv(f, encoding="utf-8", quoting=1, low_memory=False)
        df["LetoStoritve"] = year  # Add year context column
        
        # Keep only the essential columns required for trend mapping
        needed_cols = ["ZaporednaStevilkaKD", "LetoStoritve", "MesecStoritve", "KD_SKUPINA", "PUStoritveKD"]
        available_cols = [c for c in needed_cols if c in df.columns]
        
        all_dfs.append(df[available_cols])
        
    return pd.concat(all_dfs, ignore_index=True)

if __name__ == "__main__":
    base_dir = Path(__file__).parents[2]
    formatted_path = base_dir / "data" / "formatted"
    
    # 1. Combine all annual records
    df_historical = load_all_years(formatted_path)
    
    if not df_historical.empty:
        print("\n--- TOTAL CRIME COUNT BY YEAR ---")
        # Count unique criminal offenses per year
        yearly_total = df_historical.groupby("LetoStoritve")["ZaporednaStevilkaKD"].nunique()
        print(yearly_total)
        
        print("\n--- TRENDS BY MAIN CRIME GROUPS ---")
        # Track the behavior of individual crime clusters over time
        crime_trends = (
            df_historical.groupby(["LetoStoritve", "KD_SKUPINA"])["ZaporednaStevilkaKD"]
            .nunique()
            .unstack(fill_value=0)
        )
        
        # Isolate the top 5 most frequent crime clusters for preview
        top_clusters = df_historical["KD_SKUPINA"].value_counts().index[:5]
        print(crime_trends[top_clusters])
        
        # Save compiled overview matrix for later visualization plotting
        out_dir = base_dir / "data" / "analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        crime_trends.to_csv(out_dir / "historical_crime_trends.csv")
        logger.info(f"Aggregated trend statistics successfully saved to: {out_dir / 'historical_crime_trends.csv'}")