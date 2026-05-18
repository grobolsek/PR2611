"""Normalization utilities for crime analysis.

Provides a `Normalizer` class that returns normalized tables depending on
analysis goals: per-location rates (per population), hourly distribution
per city, and crime-type distribution per city. Outputs are pandas
DataFrames and can be written to CSV for further analysis.

Example usage::
    from formatting.normalization import Normalizer
    df = pd.read_csv('data/formatted/kd2024.csv')
    norm = Normalizer(df)
    rates = norm.crimes_per_population(year=2024)
    by_hour = norm.normalize_by_hour()
    dist = norm.crime_type_distribution()
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

import pandas as pd

# Ensure the workspace `src` directory is on sys.path so imports like
# `analysis.population` work when running this script directly.
_ROOT = Path(__file__).parents[2]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Import get_population directly from the population.py file to avoid
# ambiguity if a top-level module named `analysis` is present.
import importlib.util

_pop_path = _SRC / "analysis" / "population.py"
if _pop_path.exists():
    spec = importlib.util.spec_from_file_location("_analysis_population", str(_pop_path))
    _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod)  # type: ignore[attr-defined]
    get_population = _mod.get_population
else:
    raise ImportError(f"Could not find population.py at {_pop_path}")

logger = logging.getLogger(__name__)


class Normalizer:
    def __init__(self, crimes: pd.DataFrame):
        self.crimes = crimes.copy()

    def _extract_start_hour(self, ura: object) -> int | None:
        """Parse `UraStoritve` like 'HH:MM-HH:MM' and return start hour as int."""
        if pd.isna(ura):
            return None
        s = str(ura).strip()
        m = re.match(r"^(\d{1,2}):\d{2}", s)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _normalize_location(self, location: object) -> object:
        if pd.isna(location):
            return location
        text = str(location).strip()
        if text.upper() == "GPU":
            return "NI PODATKA"
        return text

    def crimes_per_population(
        self,
        by: str = "PUStoritveKD",
        year: int = 2024,
        half_year: int = 1,
        per: int = 100000,
        day_migrants: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """Compute crime counts per `by` normalized by population.

        - `by`: column in crimes DataFrame representing location (e.g. `PUStoritveKD`).
        - `year`, `half_year`: passed to `get_population` to fetch population.
        - `per`: scale (e.g., per 100000 inhabitants).

        Returns a DataFrame with columns: `location`, `crimes`, `population`, `rate_per_<per>`.
        """
        pop = get_population(year, half_year)

        # pop.region contains PU names by earlier mapping; rename to match 'by'
        pop_df = pop.rename(columns={"region": by, "sum": "population"})[[by, "population"]]

        df = self.crimes.copy()
        df[by] = df[by].apply(self._normalize_location)

        crimes_by_loc = df.groupby(by, dropna=False).size().reset_index(name="crimes").rename(columns={by: "location"})

        pop_df[by] = pop_df[by].apply(self._normalize_location)
        merged = crimes_by_loc.merge(pop_df.rename(columns={by: "location"}), on="location", how="left")
        merged["population"] = merged["population"].fillna(0).astype(int)

        # Avoid division by zero
        merged[f"rate_per_{per}"] = merged.apply(
            lambda r: (r["crimes"] / r["population"] * per) if r["population"] > 0 else None,
            axis=1,
        )

        return merged.sort_values("rate_per_%d" % per, na_position="last", ascending=False)

    def normalize_by_hour(self, city_col: str = "PUStoritveKD", hour_col: str = "UraStoritve") -> pd.DataFrame:
        """Return hourly percentage distribution of crimes per city.

        Result columns: `location`, `hour`, `count`, `pct_of_city` (0-100).
        """
        df = self.crimes.copy()
        df[city_col] = df[city_col].apply(self._normalize_location)
        df["_start_hour"] = df[hour_col].apply(self._extract_start_hour)
        df = df.dropna(subset=["_start_hour"])
        df["_start_hour"] = df["_start_hour"].astype(int)

        counts = df.groupby([city_col, "_start_hour"]).size().reset_index(name="count")
        total_by_city = counts.groupby(city_col)["count"].sum().reset_index(name="total")
        merged = counts.merge(total_by_city, on=city_col, how="left")
        merged["pct_of_city"] = merged["count"] / merged["total"] * 100
        merged["pct_of_city"] = merged["pct_of_city"].round(2).map(lambda v: f"{v:.2f}%" if pd.notna(v) else None)
        merged = merged.rename(columns={city_col: "location", "_start_hour": "hour"})
        return merged.sort_values(["location", "hour"]).reset_index(drop=True)

    def crime_type_distribution(self, city_col: str = "PUStoritveKD", crime_col: str = "KD_SKUPINA") -> pd.DataFrame:
        """Return distribution of crime types per city as percentages.

        Result columns: `location`, `crime_type`, `count`, `pct_of_city`.
        """
        df = self.crimes.copy()
        df[city_col] = df[city_col].apply(self._normalize_location)
        counts = df.groupby([city_col, crime_col]).size().reset_index(name="count")
        total_by_city = counts.groupby(city_col)["count"].sum().reset_index(name="total")
        merged = counts.merge(total_by_city, on=city_col, how="left")
        merged["pct_of_city"] = merged["count"] / merged["total"] * 100
        merged["pct_of_city"] = merged["pct_of_city"].round(2).map(lambda v: f"{v:.2f}%" if pd.notna(v) else None)
        merged = merged.rename(columns={city_col: "location", crime_col: "crime_type"})
        return merged.sort_values(["location", "pct_of_city"], ascending=[True, False]).reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    base = Path(__file__).parents[2]
    formatted = base / "data" / "formatted" / "kd2024.csv"
    out_dir = base / "data" / "normalized"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(formatted, encoding="utf-8", quoting=1, low_memory=False)
    norm = Normalizer(df)

    rates = norm.crimes_per_population(year=2024)
    rates.to_csv(out_dir / "rates_by_location_2024.csv", index=False, encoding="utf-8", quoting=1)

    by_hour = norm.normalize_by_hour()
    by_hour.to_csv(out_dir / "by_hour_by_city_2024.csv", index=False, encoding="utf-8", quoting=1)

    dist = norm.crime_type_distribution()
    dist.to_csv(out_dir / "crime_type_distribution_by_city_2024.csv", index=False, encoding="utf-8", quoting=1)

    logger.info("Wrote normalized outputs to %s", out_dir)
