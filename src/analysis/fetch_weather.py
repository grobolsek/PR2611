"""Fetch weather data for Slovenian Police Management Directorates (PU) for any year.

Uses the Open-Meteo Historical Weather API to retrieve monthly average 
temperatures and total precipitation for coordinates representing each PU.
"""

from __future__ import annotations

import logging
from pathlib import Path
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PU_COORDINATES = {
    "PU LJUBLJANA": {"lat": 46.0569, "lon": 14.5058},
    "PU MARIBOR": {"lat": 46.5547, "lon": 15.6459},
    "PU CELJE": {"lat": 46.2360, "lon": 15.2670},
    "PU KOPER": {"lat": 45.5469, "lon": 13.7294},
    "PU KRANJ": {"lat": 46.2420, "lon": 14.3556},
    "PU NOVA GORICA": {"lat": 45.9560, "lon": 13.6484},
    "PU MURSKA SOBOTA": {"lat": 46.6623, "lon": 16.1645},
    "PU NOVO MESTO": {"lat": 45.8039, "lon": 15.1689}
}

def fetch_actual_weather(year: int) -> pd.DataFrame:
    """Download historical weather data for a specific year from Open-Meteo API.
    
    Args:
        year: The year to fetch data for (e.g., 2023, 2024).
    """
    all_records = []
    
    # Dynamically set start and end dates based on the provided year
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    logger.info(f"Starting weather data download from Open-Meteo API for the year {year}...")
    
    for pu_name, coords in PU_COORDINATES.items():
        logger.info(f"Fetching data for: {pu_name}")
        
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={coords['lat']}&longitude={coords['lon']}&"
            f"start_date={start_date}&end_date={end_date}&"
            f"daily=temperature_2m_mean,precipitation_sum&timezone=Europe/Berlin"
        )
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            daily_data = data["daily"]
            df_daily = pd.DataFrame({
                "date": pd.to_datetime(daily_data["time"]),
                "temp": daily_data["temperature_2m_mean"],
                "rain": daily_data["precipitation_sum"]
            })
            
            # Dynamic month format matching your crime dataset (e.g., MM.YYYY)
            df_daily["MesecStoritve"] = df_daily["date"].dt.strftime("%m.%Y")
            
            monthly_agg = df_daily.groupby("MesecStoritve").agg(
                avg_temp=("temp", "mean"),
                precipitation_mm=("rain", "sum")
            ).reset_index()
            
            monthly_agg["PUStoritveKD"] = pu_name
            all_records.append(monthly_agg)
            
        except Exception as e:
            logger.error(f"Error downloading data for {pu_name}: {e}")
            
    if not all_records:
        return pd.DataFrame()
        
    df_weather_final = pd.concat(all_records, ignore_index=True)
    df_weather_final["avg_temp"] = df_weather_final["avg_temp"].round(2)
    df_weather_final["precipitation_mm"] = df_weather_final["precipitation_mm"].round(2)
    
    return df_weather_final

if __name__ == "__main__":
    # configure year 
    SELECTED_YEAR = 2023
    
    df_real_weather = fetch_actual_weather(year=SELECTED_YEAR)
    
    if not df_real_weather.empty:
        out_dir = Path(__file__).parents[2] / "data" / "weather"
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Output file automatically names itself based on the selected year
        out_file = out_dir / f"slovenia_weather_{SELECTED_YEAR}.csv"
        df_real_weather.to_csv(out_file, index=False, encoding="utf-8")
        
        logger.info(f"Successfully saved! Actual weather data stored in: {out_file}")
        print(df_real_weather.head(12))