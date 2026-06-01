"""Long-term Holt-Winters forecast of total monthly crime."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from dashboard import data


def render() -> None:
    st.title("🔮 Crime Forecast")
    st.caption(
        "Holt-Winters exponential smoothing (additive trend + seasonality) fit on monthly totals from `data/by_year/`.",
    )

    col_start, col_horizon = st.columns(2)
    start_year = col_start.slider("Training start year", 2000, 2020, 2010, step=1)
    horizon = col_horizon.slider("Forecast horizon (months)", 6, 36, 24, step=6)

    series = data.monthly_series(start_year)
    if series.empty:
        st.error("Could not build the historical time series from `data/by_year/`.")
        return

    forecast = data.holt_winters_forecast(horizon, start_year)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series.index,
            y=series.values,
            name=f"Historical ({start_year}+)",
            line=dict(color="royalblue"),
        ),
    )
    fig.add_trace(
        go.Scatter(
            x=forecast.index,
            y=forecast.values,
            name="Forecast",
            line=dict(color="crimson", dash="dash", width=3),
        ),
    )
    fig.update_layout(
        height=480,
        xaxis_title="Year",
        yaxis_title="Monthly offence count",
        legend=dict(orientation="h", y=1.02, yanchor="bottom"),
        margin=dict(t=10),
    )
    st.plotly_chart(fig, width='stretch')

    c1, c2, c3 = st.columns(3)
    c1.metric("Series start", series.index.min().strftime("%m.%Y"))
    c2.metric("Series end", series.index.max().strftime("%m.%Y"))
    c3.metric("Next-12-months avg", f"{forecast.head(12).mean():,.0f}")

    st.subheader("Forecast table")
    table = forecast.head(12).round().astype(int).reset_index()
    table.columns = ["Month", "Predicted offences"]
    table["Month"] = table["Month"].dt.strftime("%m.%Y")
    st.dataframe(table, width='stretch', hide_index=True)
