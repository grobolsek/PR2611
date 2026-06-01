"""Cached data-access layer for the Streamlit dashboard.

Centralises every read of the project's CSV datasets behind ``st.cache_data`` so
the (large) crime files are parsed at most once per session. Where possible the
loaders reuse the existing analysis modules in :mod:`analysis` instead of
re-implementing logic.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
FORMATTED_DIR = DATA_DIR / "formatted"
BY_YEAR_DIR = DATA_DIR / "by_year"
IMMIGRATION_DIR = DATA_DIR / "immigration"
WEATHER_DIR = DATA_DIR / "weather"
ANALYSIS_DIR = DATA_DIR / "analysis"
RELATIONS_DIR = DATA_DIR / "relations"
PROSECUTION_DIR = DATA_DIR / "prosecution_duration"

CRIME_GROUP_COL = "KD_SKUPINA"
LOCATION_COL = "PUStoritveKD"
CRIME_ID_COL = "ZaporednaStevilkaKD"
MONTH_COL = "MesecStoritve"

# Crime clusters the seminar focuses on for the correlation studies.
DEFAULT_CLUSTERS = ["Premoženjska kazniva dejanja", "Nasilje nad osebami"]

# Selector label that means "do not filter by cluster — combine all crimes".
ALL_CRIMES_LABEL = "All crimes (combined)"

# Slovenian weekday names in calendar order (data/formatted DanVTednu column).
WEEKDAY_ORDER = ["PONEDELJEK", "TOREK", "SREDA", "ČETRTEK", "PETEK", "SOBOTA", "NEDELJA"]


def _read_csv(path: Path, **kwargs: object) -> pd.DataFrame:
    """Read a project CSV, transparently falling back to cp1250 encoding."""
    try:
        return pd.read_csv(path, encoding="utf-8", quoting=1, low_memory=False, **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="cp1250", quoting=1, low_memory=False, **kwargs)


# --------------------------------------------------------------------------- #
# Formatted per-person crime files (data/formatted/kd<YYYY>.csv)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def formatted_years() -> list[int]:
    """Return the sorted years for which a formatted crime file exists."""
    years = []
    for f in FORMATTED_DIR.glob("*.csv"):
        m = re.search(r"(\d{4})", f.stem)
        if m:
            years.append(int(m.group(1)))
    return sorted(set(years))


def _formatted_path(year: int) -> Path | None:
    for stem in (f"kd{year}", f"KD{year}"):
        p = FORMATTED_DIR / f"{stem}.csv"
        if p.exists():
            return p
    matches = list(FORMATTED_DIR.glob(f"*{year}.csv"))
    return matches[0] if matches else None


@st.cache_data(show_spinner="Loading crime data…")
def load_formatted(year: int, columns: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Load a formatted crime file, optionally restricting to ``columns``.

    Restricting columns keeps memory low — each yearly file holds hundreds of
    thousands of person-level rows.
    """
    path = _formatted_path(year)
    if path is None:
        return pd.DataFrame()
    usecols = list(columns) if columns else None
    if usecols:
        header = _read_csv(path, nrows=0)
        usecols = [c for c in usecols if c in header.columns]
    return _read_csv(path, usecols=usecols)


@st.cache_data(show_spinner="Aggregating yearly totals…")
def yearly_unique_totals() -> pd.Series:
    """Count unique criminal offences (not person-rows) per formatted year."""
    totals: dict[int, int] = {}
    for year in formatted_years():
        df = load_formatted(year, columns=(CRIME_ID_COL,))
        if not df.empty:
            totals[year] = int(df[CRIME_ID_COL].nunique())
    return pd.Series(totals, name="unique_crimes").sort_index()


@st.cache_data(show_spinner="Building crime-group trend matrix…")
def crime_group_trends() -> pd.DataFrame:
    """Year × crime-cluster matrix of unique offence counts.

    Uses the pre-computed ``data/analysis/historical_crime_trends.csv`` when it
    exists, otherwise rebuilds it from the formatted files.
    """
    cached = ANALYSIS_DIR / "historical_crime_trends.csv"
    if cached.exists():
        df = pd.read_csv(cached, encoding="utf-8")
        return df.set_index(df.columns[0])

    frames = []
    for year in formatted_years():
        df = load_formatted(year, columns=(CRIME_ID_COL, CRIME_GROUP_COL))
        if df.empty:
            continue
        counts = df.groupby(CRIME_GROUP_COL)[CRIME_ID_COL].nunique()
        counts.name = year
        frames.append(counts)
    if not frames:
        return pd.DataFrame()
    matrix = pd.concat(frames, axis=1).T.fillna(0).astype(int)
    matrix.index.name = "LetoStoritve"
    return matrix


def _temporal_bucket(series: pd.Series, dimension: str) -> pd.Series:
    """Map a raw crime column to a month (1–12), weekday name, or hour (0–23)."""
    text = series.astype(str).str.strip()
    if dimension == "month":
        return pd.to_numeric(text.str.split(".").str[0], errors="coerce")
    if dimension == "hour":
        return pd.to_numeric(text.str.extract(r"^(\d{1,2})")[0], errors="coerce")
    return text.str.upper().replace("NAN", pd.NA)


@st.cache_data(show_spinner="Building temporal trend matrix…")
def crime_temporal_trends(dimension: str) -> pd.DataFrame:
    """Bucket × crime-cluster matrix of unique offences, summed over all years.

    ``dimension`` is one of ``"month"`` (1–12), ``"weekday"`` (Mon–Sun) or
    ``"hour"`` (0–23). Buckets are ordered and gap-filled with zeros.
    """
    col = {"month": MONTH_COL, "weekday": "DanVTednu", "hour": "UraStoritve"}[dimension]
    frames = []
    for year in formatted_years():
        df = load_formatted(year, columns=(col, CRIME_GROUP_COL, CRIME_ID_COL))
        if df.empty or col not in df.columns:
            continue
        df = df.copy()
        df["bucket"] = _temporal_bucket(df[col], dimension)
        df = df.dropna(subset=["bucket", CRIME_GROUP_COL])
        if dimension in ("month", "hour"):
            df["bucket"] = df["bucket"].astype(int)
        frames.append(df.groupby(["bucket", CRIME_GROUP_COL])[CRIME_ID_COL].nunique())
    if not frames:
        return pd.DataFrame()

    matrix = pd.concat(frames).groupby(level=[0, 1]).sum().unstack(CRIME_GROUP_COL)

    if dimension == "month":
        matrix = matrix.reindex(range(1, 13))
        matrix.index.name = "Month"
    elif dimension == "hour":
        matrix = matrix.reindex(range(24))
        matrix.index.name = "Hour"
    else:
        matrix = matrix.reindex([d for d in WEEKDAY_ORDER if d in matrix.index])
        matrix.index.name = "Day of week"
    return matrix.fillna(0).astype(int)


@st.cache_data(show_spinner="Summarising a year…")
def year_summary(year: int) -> dict[str, object]:
    """Headline figures for a single formatted year."""
    df = load_formatted(
        year,
        columns=(CRIME_ID_COL, CRIME_GROUP_COL, LOCATION_COL, "VrstaOsebe", "Spol"),
    )
    if df.empty:
        return {}
    suspects = df[df["VrstaOsebe"].astype(str).str.contains("OSUMLJ|OBTO|OVAD", case=False, na=False)] if "VrstaOsebe" in df.columns else df
    return {
        "unique_crimes": int(df[CRIME_ID_COL].nunique()),
        "person_rows": len(df),
        "n_clusters": int(df[CRIME_GROUP_COL].nunique()),
        "n_locations": int(df[LOCATION_COL].nunique()),
        "top_cluster": df[CRIME_GROUP_COL].value_counts().idxmax(),
        "top_location": df[LOCATION_COL].value_counts().idxmax(),
        "suspect_rows": len(suspects),
    }


@st.cache_data(show_spinner="Profiling suspects…")
def suspect_profile(year: int) -> dict[str, pd.DataFrame]:
    """Suspect-only breakdowns for a year.

    Filters to suspect records (``VrstaOsebe`` containing ``OSUMLJ``) and returns
    DataFrames keyed ``top_crimes``, ``gender`` and ``citizenship`` (Slovenian vs
    foreign nationality). Empty dict when no suspect rows exist.
    """
    df = load_formatted(year, columns=("VrstaOsebe", "Spol", "Drzavljanstvo", CRIME_GROUP_COL))
    if df.empty or "VrstaOsebe" not in df.columns:
        return {}
    suspects = df[df["VrstaOsebe"].astype(str).str.contains("OSUMLJ", na=False)]
    if suspects.empty:
        return {}

    def _counts(col: str, name: str) -> pd.DataFrame:
        return suspects[col].value_counts(dropna=False).rename_axis(name).reset_index(name="count")

    return {
        "top_crimes": _counts(CRIME_GROUP_COL, "crime").head(10),
        "gender": _counts("Spol", "gender"),
        "citizenship": _counts("Drzavljanstvo", "citizenship"),
    }


@st.cache_data(show_spinner="Profiling suspects (all years)…")
def suspect_profile_all() -> dict[str, pd.DataFrame]:
    """Suspect-only breakdowns summed across every formatted year.

    Same shape as :func:`suspect_profile` (``top_crimes``/``gender``/
    ``citizenship``), but aggregated over all available years.
    """
    col_map = {"crime": CRIME_GROUP_COL, "gender": "Spol", "citizenship": "Drzavljanstvo"}
    totals = {key: pd.Series(dtype="float64") for key in col_map}
    for year in formatted_years():
        df = load_formatted(year, columns=("VrstaOsebe", "Spol", "Drzavljanstvo", CRIME_GROUP_COL))
        if df.empty or "VrstaOsebe" not in df.columns:
            continue
        suspects = df[df["VrstaOsebe"].astype(str).str.contains("OSUMLJ", na=False)]
        for key, col in col_map.items():
            if col in suspects.columns:
                totals[key] = totals[key].add(suspects[col].value_counts(dropna=False), fill_value=0)

    if all(series.empty for series in totals.values()):
        return {}

    def _frame(key: str, name: str, top: int | None = None) -> pd.DataFrame:
        series = totals[key].astype(int).sort_values(ascending=False)
        if top is not None:
            series = series.head(top)
        return series.rename_axis(name).reset_index(name="count")

    return {
        "top_crimes": _frame("crime", "crime", top=10),
        "gender": _frame("gender", "gender"),
        "citizenship": _frame("citizenship", "citizenship"),
    }


# --------------------------------------------------------------------------- #
# Geography (re-implemented from analysis.normalization to avoid its deleted
# population.py dependency; absolute counts + per-city distributions).
# --------------------------------------------------------------------------- #
def _normalize_location(loc: object) -> object:
    if pd.isna(loc):
        return loc
    text = str(loc).strip()
    return "NI PODATKA" if text.upper() == "GPU" else text


@st.cache_data(show_spinner="Fetching population…")
def population_by_pu(year: int, half_year: int = 1) -> pd.Series:
    """Population per police directorate (PU) from SiStat, indexed by PU name.

    Returns an empty Series if the SiStat API is unreachable, so callers can
    degrade gracefully without population data.
    """
    from analysis.population import get_population

    try:
        pop = get_population(year, half_year)
    except Exception:
        return pd.Series(dtype="float64")
    return pop.set_index("region")["sum"]


@st.cache_data(show_spinner="Computing location statistics…")
def location_counts(year: int, suspects_only: bool = True) -> pd.DataFrame:
    """Crime counts per police directorate (PU) for a year.

    ``percent`` is the normalized per-capita rate (crimes / population), shown
    as crimes per 100 inhabitants; ``population`` is the PU population.
    """
    df = load_formatted(year, columns=(LOCATION_COL, "VrstaOsebe", CRIME_ID_COL))
    if df.empty:
        return pd.DataFrame()
    if suspects_only and "VrstaOsebe" in df.columns:
        df = df[df["VrstaOsebe"] == "OVADENI OSUMLJENEC"]
    df[LOCATION_COL] = df[LOCATION_COL].apply(_normalize_location)
    stats = (
        df.groupby(LOCATION_COL)
        .agg(count=(LOCATION_COL, "size"), unique_crimes=(CRIME_ID_COL, "nunique"))
        .reset_index()
        .rename(columns={LOCATION_COL: "location"})
        .sort_values("count", ascending=False)
    )
    population = population_by_pu(year)
    stats["population"] = stats["location"].map(population).astype("Int64")
    stats["percent"] = (stats["count"] / stats["population"] * 100).round(4)
    return stats


@st.cache_data(show_spinner="Computing crime-type distribution…")
def crime_type_distribution(year: int) -> pd.DataFrame:
    """Share of each crime cluster per location."""
    df = load_formatted(year, columns=(LOCATION_COL, CRIME_GROUP_COL))
    if df.empty:
        return pd.DataFrame()
    df[LOCATION_COL] = df[LOCATION_COL].apply(_normalize_location)
    counts = df.groupby([LOCATION_COL, CRIME_GROUP_COL]).size().reset_index(name="count")
    totals = counts.groupby(LOCATION_COL)["count"].transform("sum")
    counts["pct_of_city"] = (counts["count"] / totals * 100).round(2)
    return counts.rename(columns={LOCATION_COL: "location", CRIME_GROUP_COL: "crime_type"})


# --------------------------------------------------------------------------- #
# Long-term forecasting series (data/by_year/<YYYY>.csv) — reads only the month
# column so the multi-GB folder stays cheap to scan.
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Building the monthly time series…")
def monthly_series(start_year: int = 2010, end_year: int = 2023) -> pd.Series:
    """Monthly total crime counts between ``start_year`` and ``end_year``, interpolated."""
    files = sorted(f for f in BY_YEAR_DIR.glob("*.csv") if re.match(r"^\d{4}$", f.stem))
    records = []
    for path in files:
        year = int(path.stem)
        if year < start_year or year > end_year:
            continue
        header = _read_csv(path, nrows=0)
        month_col = "MesecStoritve" if "MesecStoritve" in header.columns else "Mesec"
        if month_col not in header.columns:
            continue
        df = _read_csv(path, usecols=[month_col])
        monthly = df.groupby(month_col).size().reset_index(name="total_crime")
        monthly[month_col] = monthly[month_col].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        monthly["Date_Str"] = monthly[month_col].apply(
            lambda x: f"{x.zfill(2)}.{year}" if "." not in x else x,
        )
        records.append(monthly[["Date_Str", "total_crime"]])
    if not records:
        return pd.Series(dtype="float64")
    df_all = pd.concat(records, ignore_index=True)
    df_all["Datum"] = pd.to_datetime(df_all["Date_Str"], format="%m.%Y", errors="coerce")
    df_all = df_all.dropna(subset=["Datum"]).sort_values("Datum")
    series = df_all.groupby("Datum")["total_crime"].sum().asfreq("MS")
    return series.replace(0, pd.NA).interpolate(method="linear")


@st.cache_data(show_spinner="Fitting Holt-Winters forecast…")
def holt_winters_forecast(months: int = 24, start_year: int = 2010) -> pd.Series:
    """Forecast total monthly crime ``months`` ahead with Holt-Winters."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    series = monthly_series(start_year)
    if series.empty:
        return pd.Series(dtype="float64")
    series = series.astype(float)
    model = ExponentialSmoothing(series, trend="add", seasonal="add", seasonal_periods=12).fit()
    return model.forecast(months).clip(lower=0)


# --------------------------------------------------------------------------- #
# Auxiliary datasets
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_immigration() -> pd.DataFrame:
    """Monthly issued residence-permit counts.

    Generates the trends CSV from the source workbooks via
    ``analysis.process_monthly_immigration`` when it is missing.
    """
    from analysis.process_monthly_immigration import generate_monthly_immigration_file

    path = IMMIGRATION_DIR / "monthly_immigration_trends.csv"
    if not path.exists():
        generate_monthly_immigration_file(IMMIGRATION_DIR)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8")
    df[MONTH_COL] = df[MONTH_COL].astype(str).str.strip()
    df["Datum"] = pd.to_datetime(df[MONTH_COL], format="%m.%Y", errors="coerce")
    return df.sort_values("Datum")


@st.cache_data(show_spinner="Ranking clusters by immigration correlation…")
def immigration_cluster_correlations(year: int) -> pd.Series:
    """Pearson r between each crime cluster's monthly count and issued permits.

    Returns a Series indexed by cluster label (plus :data:`ALL_CRIMES_LABEL` for
    all crimes combined), sorted by absolute correlation strength descending.
    Empty if crime or immigration data is unavailable for the year.
    """
    from analysis import monthly_crime_immigration_corr as mci

    crimes = load_formatted(year, columns=(CRIME_GROUP_COL, MONTH_COL))
    imm = load_immigration()
    if crimes.empty or imm.empty:
        return pd.Series(dtype="float64")

    def _pad(month: str) -> str:
        return f"0{month}" if len(month) == 6 else month

    imm = imm.copy()
    imm[MONTH_COL] = imm[MONTH_COL].astype(str).str.strip().map(_pad)

    clusters = sorted(crimes[CRIME_GROUP_COL].dropna().unique())
    results: dict[str, float] = {}
    for label, cluster in [(ALL_CRIMES_LABEL, None), *((c, c) for c in clusters)]:
        monthly = mci.get_monthly_crime_counts(crimes, cluster)
        if monthly.empty:
            continue
        monthly[MONTH_COL] = monthly[MONTH_COL].map(_pad)
        merged = monthly.merge(imm, on=MONTH_COL, how="inner")
        if len(merged) < 2:
            continue
        r = merged["crime_count"].corr(merged["Izdana_Dovoljenja_Mesec"])
        if pd.notna(r):
            results[label] = float(r)

    series = pd.Series(results)
    return series.reindex(series.abs().sort_values(ascending=False).index)


@st.cache_data(show_spinner=False)
def weather_years() -> list[int]:
    """Years available for weather analysis.

    Any year with a formatted crime file qualifies — weather for missing years
    is fetched on demand by :func:`load_weather`.
    """
    return formatted_years()


@st.cache_data(show_spinner="Fetching weather…")
def load_weather(year: int) -> pd.DataFrame:
    """Monthly weather per PU for ``year``.

    Downloads it from the Open-Meteo archive via ``analysis.fetch_weather`` and
    caches it to ``data/weather/`` when the file is missing.
    """
    from analysis.fetch_weather import fetch_actual_weather

    path = WEATHER_DIR / f"slovenia_weather_{year}.csv"
    if not path.exists():
        try:
            df = fetch_actual_weather(year)
        except Exception:
            df = pd.DataFrame()
        if not df.empty:
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(path, index=False, encoding="utf-8")
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8")


@st.cache_data(show_spinner="Building prosecution analysis…")
def load_prosecution() -> pd.DataFrame:
    """Prosecution-duration analysis.

    Generated from the formatted crime files (and the person-relations table,
    itself generated if missing) via ``analysis.prosecution_duration`` when the
    CSV is absent.
    """
    from analysis.prosecution_duration import build_prosecution_analysis
    from analysis.relations import build_relations

    path = PROSECUTION_DIR / "prosecution_analysis.csv"
    relations_path = RELATIONS_DIR / "person_relations.csv"
    if not path.exists():
        try:
            if not relations_path.exists():
                build_relations(FORMATTED_DIR, relations_path)
            build_prosecution_analysis(FORMATTED_DIR, relations_path, path)
        except Exception:
            return pd.DataFrame()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8", quoting=1)


@st.cache_data(show_spinner="Building person-relations table…")
def load_relations() -> pd.DataFrame:
    """Person–crime relations, generated from the formatted files when missing."""
    from analysis.relations import build_relations

    path = RELATIONS_DIR / "person_relations.csv"
    if not path.exists():
        try:
            build_relations(FORMATTED_DIR, path)
        except Exception:
            return pd.DataFrame()
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8", quoting=1)
