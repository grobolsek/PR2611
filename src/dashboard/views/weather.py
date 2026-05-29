"""Crime ⇄ weather correlation, reusing analysis.weather_analysis."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from analysis import weather_analysis

from dashboard import data


def render() -> None:
    st.title("🌦️ Weather Correlation")
    st.caption(
        "Pearson correlation between monthly crime counts and temperature / "
        "precipitation per region, via `analysis.weather_analysis`.",
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
    default_idx = clusters.index("Nasilje nad osebami") if "Nasilje nad osebami" in clusters else 0
    cluster = st.selectbox("Crime cluster", clusters, index=default_idx)

    merged = weather_analysis.get_crime_weather_data(crimes, weather, crime_cluster=cluster)
    if merged.empty:
        st.warning("No overlapping crime/weather rows for this cluster.")
        return

    # The weather CSVs ship avg_temp / precipitation_mm columns, so pass them
    # explicitly rather than relying on the function's Slovenian-named defaults.
    metrics = [c for c in ("avg_temp", "precipitation_mm") if c in merged.columns]
    corr = weather_analysis.compute_correlation(merged, metrics=metrics)

    st.subheader("Correlation matrix")
    st.dataframe(
        corr.style.background_gradient(cmap="RdBu", vmin=-1, vmax=1).format("{:.3f}"),
        use_container_width=True,
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
            y="stevilka_zlocinov",
            color=data.LOCATION_COL if data.LOCATION_COL in merged.columns else None,
            trendline="ols",
            labels={"stevilka_zlocinov": "Monthly crime count", xcol: label},
        )
        fig.update_layout(height=460, legend_title="")
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Merged crime + weather rows"):
        st.dataframe(merged, use_container_width=True, hide_index=True)
