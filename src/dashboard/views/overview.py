"""Landing page: dataset scope and headline figures."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard import data

_GENDER_LABELS = {"MOŠKI": "Male", "ŽENSKI": "Female", "PRAVNA OSEBA": "Legal entity"}
_CITIZENSHIP_LABELS = {"SLOVENSKO": "Slovenian", "TUJE": "Foreign"}


def _suspect_section(year_range: str) -> None:
    """Most-popular-crimes bar plus gender / citizenship demographics for suspects."""
    st.subheader(f"🧑‍⚖️ Suspect profile — {year_range}")
    st.caption("Suspect records only (OVADENI / NEOVADENI OSUMLJENEC), all years combined.")
    profile = data.suspect_profile_all()
    if not profile:
        st.info("No suspect records found.")
        return

    st.markdown("**Most popular crimes**")
    fig_c = px.bar(
        profile["top_crimes"].sort_values("count"),
        x="count",
        y="crime",
        orientation="h",
        color="count",
        color_continuous_scale="Reds",
        labels={"count": "Suspect records", "crime": ""},
    )
    fig_c.update_layout(height=380, coloraxis_showscale=False, margin=dict(t=10))
    st.plotly_chart(fig_c, width='stretch')

    st.markdown("**Demographics**")
    d1, d2 = st.columns(2)
    with d1:
        gender = profile["gender"].assign(gender=lambda d: d["gender"].map(_GENDER_LABELS).fillna(d["gender"]))
        fig_g = px.pie(gender, names="gender", values="count", hole=0.45, title="Gender")
        fig_g.update_layout(height=320, margin=dict(t=40))
        fig_g.update_traces(textinfo="percent+label")
        st.plotly_chart(fig_g, width='stretch')
    with d2:
        citizenship = profile["citizenship"].assign(
            citizenship=lambda d: d["citizenship"].map(_CITIZENSHIP_LABELS).fillna(d["citizenship"]),
        )
        fig_n = px.pie(citizenship, names="citizenship", values="count", hole=0.45, title="Slovenian vs foreign")
        fig_n.update_layout(height=320, margin=dict(t=40))
        fig_n.update_traces(textinfo="percent+label")
        st.plotly_chart(fig_n, width='stretch')


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
        st.plotly_chart(fig, width='stretch')

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
    _suspect_section(f"{min(years)}–{max(years)}")

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
