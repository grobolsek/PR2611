"""Crime ⇄ weather correlation, reusing analysis.weather_analysis."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from analysis import weather_analysis
from dashboard import data


def render() -> None:
    st.title("🌦️ Weather Correlation")
    st.caption(
        "Pearson correlation between monthly crime counts and temperature / precipitation per region, via `analysis.weather_analysis`.",
    )

    wyears = data.weather_years()
    if not wyears:
        st.warning("No weather files under `data/weather/`.")
        return

    year = st.selectbox("Year", wyears[::-1])
    weather = data.load_weather(year)
    crimes = data.load_formatted(
        year,
        columns=(data.CRIME_GROUP_COL, data.LOCATION_COL, data.MONTH_COL),
    )
    if crimes.empty or weather.empty:
        st.warning(f"Missing crime or weather data for {year}.")
        return

    clusters = sorted(crimes[data.CRIME_GROUP_COL].dropna().unique())
    options = [data.ALL_CRIMES_LABEL, *clusters]
    default_idx = options.index("Nasilje nad osebami") if "Nasilje nad osebami" in options else 0
    cluster = st.selectbox("Crime cluster", options, index=default_idx)
    crime_cluster = None if cluster == data.ALL_CRIMES_LABEL else cluster

    merged = weather_analysis.get_crime_weather_data(crimes, weather, crime_cluster=crime_cluster)
    if merged.empty:
        st.warning("No overlapping crime/weather rows for this cluster.")
        return

    per_capita = st.toggle(
        "Per 100 inhabitants",
        value=False,
        help="Normalize monthly crime counts by each region's population (via SiStat).",
    )
    ycol, ylabel = "stevilka_zlocinov", "Monthly crime count"
    if per_capita:
        population = data.population_by_pu(year)
        merged["population"] = merged[data.LOCATION_COL].map(population)
        merged = merged[merged["population"].fillna(0) > 0]
        if merged.empty:
            st.warning("No population data available for these regions (SiStat API unreachable).")
            return
        merged["crimes_per_100"] = merged["stevilka_zlocinov"] / merged["population"] * 100
        ycol, ylabel = "crimes_per_100", "Monthly crimes per 100 inhabitants"

    # The weather CSVs ship avg_temp / precipitation_mm columns, so pass them
    # explicitly rather than relying on the function's Slovenian-named defaults.
    metrics = [c for c in ("avg_temp", "precipitation_mm") if c in merged.columns]
    corr = merged[[ycol, *metrics]].corr()

    st.subheader("Correlation matrix")
    st.dataframe(
        corr.style.background_gradient(cmap="RdBu", vmin=-1, vmax=1).format("{:.3f}"),
        width='stretch',
    )

    metric_map = {
        "Average temperature": "avg_temp",
        "Precipitation (mm)": "precipitation_mm",
    }
    available = {k: v for k, v in metric_map.items() if v in merged.columns}
    if available:
        label = st.radio("Compare crime against", list(available), horizontal=True)
        xcol = available[label]
        fig = px.scatter(
            merged,
            x=xcol,
            y=ycol,
            color=data.LOCATION_COL if data.LOCATION_COL in merged.columns else None,
            trendline="ols",
            labels={ycol: ylabel, xcol: label},
        )
        fig.update_layout(height=460, legend_title="")
        st.plotly_chart(fig, width='stretch')

    with st.expander("Merged crime + weather rows"):
        st.dataframe(merged, width='stretch', hide_index=True)
