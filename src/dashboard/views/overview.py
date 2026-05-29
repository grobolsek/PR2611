"""Landing page: dataset scope and headline figures."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard import data


def render() -> None:
    st.title("🇸🇮 Slovenian Crime Data Explorer")
    st.markdown(
        "An interactive companion to the data-mining seminar. It combines police "
        "crime records with **weather**, **immigration** and **prosecution** data to "
        "explore long-term trends, geography and predictive models.",
    )

    years = data.formatted_years()
    if not years:
        st.error("No formatted crime files found under `data/formatted/`.")
        return

    totals = data.yearly_unique_totals()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Years covered", f"{min(years)}–{max(years)}")
    c2.metric("Total offences (all years)", f"{int(totals.sum()):,}")
    c3.metric("Annual files", len(years))
    c4.metric("Crime clusters", data.crime_group_trends().shape[1])

    st.divider()

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Total recorded offences per year")
        fig = px.bar(
            totals.reset_index().rename(columns={"index": "Year", "unique_crimes": "Offences"}),
            x="Year",
            y="Offences",
            color="Offences",
            color_continuous_scale="Blues",
        )
        fig.update_layout(coloraxis_showscale=False, height=380, margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Inspect a year")
        year = st.selectbox("Year", years[::-1], key="overview_year")
        summary = data.year_summary(year)
        if summary:
            st.metric("Unique offences", f"{summary['unique_crimes']:,}")
            st.metric("Person records", f"{summary['person_rows']:,}")
            st.metric("Suspect records", f"{summary['suspect_rows']:,}")
            st.caption(f"Top cluster: **{summary['top_cluster']}**")
            st.caption(f"Top region: **{summary['top_location']}**")

    st.divider()
    with st.expander("About the data sources"):
        st.markdown(
            """
            - **`data/formatted/kd<YYYY>.csv`** — per-person police crime records (2009–2024).
            - **`data/by_year/<YYYY>.csv`** — raw annual files (1942–2025) used for the long-term forecast.
            - **`data/immigration/`** — monthly issued residence permits (GOV.SI).
            - **`data/weather/`** — monthly temperature & precipitation per police directorate (Open-Meteo).
            - **`data/prosecution_duration/`**, **`data/relations/`** — derived person ⇄ outcome tables.
            """,
        )
