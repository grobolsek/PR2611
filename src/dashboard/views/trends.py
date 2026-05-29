"""Historical trends across years and crime clusters."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard import data


def render() -> None:
    st.title("📈 Historical Trends")
    st.caption("Long-term structural shifts in recorded crime, by cluster (data/analysis/historical_crime_trends.csv).")

    trends = data.crime_group_trends()
    if trends.empty:
        st.warning("No trend data available.")
        return

    trends.index = trends.index.astype(int)
    clusters = list(trends.columns)
    totals_by_cluster = trends.sum().sort_values(ascending=False)
    default = list(totals_by_cluster.head(5).index)

    selected = st.multiselect("Crime clusters", clusters, default=default)
    normalize = st.toggle("Show as share of yearly total (%)", value=False)

    if not selected:
        st.info("Pick at least one crime cluster.")
        return

    plot_df = trends[selected].copy()
    ylabel = "Unique offences"
    if normalize:
        plot_df = plot_df.div(trends.sum(axis=1), axis=0) * 100
        ylabel = "Share of all offences (%)"

    long = plot_df.reset_index().melt(id_vars=trends.index.name or "index", var_name="Cluster", value_name=ylabel)
    xcol = long.columns[0]
    fig = px.line(long, x=xcol, y=ylabel, color="Cluster", markers=True)
    fig.update_layout(height=460, xaxis_title="Year", legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Biggest movers")
        first, last = trends.index.min(), trends.index.max()
        change = (trends.loc[last] - trends.loc[first]).sort_values(ascending=False)
        st.caption(f"Absolute change {first} → {last}")
        st.dataframe(
            change.reset_index().rename(columns={"index": "Cluster", 0: "Change"}),
            use_container_width=True,
            hide_index=True,
        )
    with col2:
        st.subheader("Cluster totals (all years)")
        fig2 = px.pie(
            values=totals_by_cluster.values,
            names=totals_by_cluster.index,
            hole=0.45,
        )
        fig2.update_layout(height=380, showlegend=False)
        fig2.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Raw trend matrix"):
        st.dataframe(trends, use_container_width=True)
