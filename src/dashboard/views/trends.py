"""Historical trends across years and crime clusters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import plotly.express as px
import streamlit as st

from dashboard import data

if TYPE_CHECKING:
    import pandas as pd

_DIMENSIONS = {"Year": "year", "Month": "month", "Day of week": "weekday", "Hour of day": "hour"}


def _side_panel(trends: pd.DataFrame, dimension: str, dim_label: str) -> None:
    """Left-column summary: biggest movers (year) or totals by time bucket."""
    if dimension == "year":
        st.subheader("Biggest movers")
        first, last = trends.index.min(), trends.index.max()
        change = (trends.loc[last] - trends.loc[first]).sort_values(ascending=False)
        st.caption(f"Absolute change {first} → {last}")
        table = change.reset_index().rename(columns={"index": "Cluster", 0: "Change"})
    else:
        st.subheader(f"Offences by {dim_label.lower()}")
        by_bucket = trends.sum(axis=1)
        st.caption(f"Peak: {by_bucket.idxmax()} ({by_bucket.max():,} offences)")
        table = by_bucket.reset_index().rename(columns={trends.index.name: dim_label, 0: "Offences"})
    st.dataframe(table, width='stretch', hide_index=True)


def render() -> None:
    st.title("📈 Historical Trends")
    st.caption("Long-term structural shifts in recorded crime, by cluster and time dimension.")

    dim_label = st.radio("Break down by", list(_DIMENSIONS), horizontal=True)
    dimension = _DIMENSIONS[dim_label]

    if dimension == "year":
        trends = data.crime_group_trends()
        if not trends.empty:
            trends.index = trends.index.astype(int)
    else:
        trends = data.crime_temporal_trends(dimension)
    if trends.empty:
        st.warning("No trend data available.")
        return

    totals_by_cluster = trends.sum().sort_values(ascending=False)

    # Offer an "All crimes (combined)" pseudo-cluster that sums every cluster.
    options = [data.ALL_CRIMES_LABEL, *totals_by_cluster.index]
    selected = st.multiselect("Crime clusters", options, default=[data.ALL_CRIMES_LABEL])
    normalize = st.toggle(f"Show as share of {dim_label.lower()} total (%)", value=False)

    if not selected:
        st.info("Pick at least one crime cluster.")
        return

    plot_source = trends.copy()
    plot_source[data.ALL_CRIMES_LABEL] = trends.sum(axis=1)
    plot_df = plot_source[selected].copy()
    ylabel = "Unique offences"
    if normalize:
        plot_df = plot_df.div(trends.sum(axis=1), axis=0) * 100
        ylabel = "Share of all offences (%)"

    long = plot_df.reset_index().melt(id_vars=trends.index.name or "index", var_name="Cluster", value_name=ylabel)
    xcol = long.columns[0]
    fig = px.line(long, x=xcol, y=ylabel, color="Cluster", markers=True)
    fig.update_layout(height=460, xaxis_title=dim_label, legend_title="")
    st.plotly_chart(fig, width='stretch')

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        _side_panel(trends, dimension, dim_label)
    with col2:
        st.subheader("Cluster totals (all years)")
        fig2 = px.pie(
            values=totals_by_cluster.values,
            names=totals_by_cluster.index,
            hole=0.45,
        )
        fig2.update_layout(height=380, showlegend=False)
        fig2.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig2, width='stretch')

    with st.expander("Raw trend matrix"):
        st.dataframe(trends, width='stretch')
