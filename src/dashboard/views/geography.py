"""Geographic breakdown by police directorate (PU)."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard import data


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

    fig = px.bar(
        counts,
        x="count",
        y="location",
        orientation="h",
        color="count",
        color_continuous_scale="Reds",
        labels={"count": "Records", "location": ""},
    )
    fig.update_layout(
        height=460,
        coloraxis_showscale=False,
        yaxis=dict(categoryorder="total ascending"),
        margin=dict(t=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(counts, use_container_width=True, hide_index=True)

    st.divider()
    tab_hour, tab_type = st.tabs(["⏰ Hourly pattern", "🏷️ Crime mix per region"])

    with tab_hour:
        hourly = data.hourly_distribution(year)
        if hourly.empty:
            st.info("No usable `UraStoritve` values for this year.")
        else:
            locations = sorted(hourly["location"].unique())
            picked = st.multiselect(
                "Regions",
                locations,
                default=[loc for loc in counts["location"].head(4) if loc in locations],
                key="hour_regions",
            )
            sub = hourly[hourly["location"].isin(picked)] if picked else hourly
            fig_h = px.line(
                sub,
                x="hour",
                y="pct_of_city",
                color="location",
                markers=True,
                labels={"hour": "Hour of day", "pct_of_city": "% of region's crime"},
            )
            fig_h.update_layout(height=420, legend_title="")
            st.plotly_chart(fig_h, use_container_width=True)

    with tab_type:
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
            st.plotly_chart(fig_t, use_container_width=True)
