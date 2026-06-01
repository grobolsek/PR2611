"""Geographic breakdown by police directorate (PU)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import plotly.express as px
import streamlit as st

from dashboard import data

if TYPE_CHECKING:
    import pandas as pd
    import plotly.graph_objects as go


def _hbar(df: pd.DataFrame, value_col: str, label: str, color_scale: str) -> go.Figure:
    """Horizontal bar chart of ``value_col`` per location, sorted descending."""
    fig = px.bar(
        df.sort_values(value_col, ascending=False),
        x=value_col,
        y="location",
        orientation="h",
        color=value_col,
        color_continuous_scale=color_scale,
        labels={value_col: label, "location": ""},
    )
    fig.update_layout(
        height=460,
        coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(t=10),
    )
    return fig


def render() -> None:
    st.title("🗺️ Geographic Analysis")
    st.caption("Where crime is recorded, when it happens, and what kind — per police directorate (PU).")

    years = data.formatted_years()
    if not years:
        st.warning("No formatted crime files found.")
        return

    col_y, col_s = st.columns([1, 2])
    year = col_y.selectbox("Year", years[::-1])
    suspects_only = col_s.toggle(
        "Count only suspects (OVADENI OSUMLJENEC)",
        value=True,
        help="Mirrors the seminar's location_analysis.py, which filters to charged suspects.",
    )

    counts = data.location_counts(year, suspects_only=suspects_only)
    if counts.empty:
        st.warning("No data for this year.")
        return

    col_count, col_rate = st.columns(2)

    with col_count:
        st.subheader("Records")
        st.plotly_chart(_hbar(counts, "count", "Records", "Reds"), width='stretch')

    with col_rate:
        st.subheader("Per 100 inhabitants")
        rate = counts.dropna(subset=["percent"])
        if rate.empty:
            st.info("No population data available (SiStat API unreachable).")
        else:
            st.plotly_chart(
                _hbar(rate, "percent", "Records per 100 inhabitants", "Blues"),
                width='stretch',
            )

    st.dataframe(
        counts,
        width='stretch',
        hide_index=True,
        column_config={
            "location": "Region",
            "count": "Records",
            "unique_crimes": "Unique crimes",
            "population": st.column_config.NumberColumn("Population", format="%d"),
            "percent": st.column_config.NumberColumn(
                "Per 100 inhabitants",
                help="Normalized rate: records / population × 100.",
                format="%.4f",
            ),
        },
    )

    st.divider()
    st.subheader("🏷️ Crime mix per region")
    dist = data.crime_type_distribution(year)
    if dist.empty:
        st.info("No data.")
    else:
        region = st.selectbox("Region", sorted(dist["location"].unique()), key="type_region")
        sub = dist[dist["location"] == region].sort_values("count", ascending=False)
        fig_t = px.bar(
            sub,
            x="count",
            y="crime_type",
            orientation="h",
            text="pct_of_city",
            labels={"count": "Records", "crime_type": ""},
        )
        fig_t.update_layout(height=520, yaxis=dict(categoryorder="total ascending"), margin=dict(t=10))
        fig_t.update_traces(texttemplate="%{text}%", textposition="outside")
        st.plotly_chart(fig_t, width='stretch')
