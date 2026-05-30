"""Prosecution-duration and case-outcome analysis."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from dashboard import data


def render() -> None:
    st.title("⚖️ Prosecution & Outcomes")
    st.caption("How long cases take to close and how persons' outcomes break down (data/prosecution_duration/).")

    df = data.load_prosecution()
    if df.empty:
        st.warning("No prosecution analysis found. Run `analysis.prosecution_duration` first.")
        return

    # Filter to plausible durations (closing year >= crime year, within ~30y).
    clean = df[(df["ProsecutionDuration"] >= 0) & (df["ProsecutionDuration"] <= 30)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Crime groups", f"{len(df):,}")
    c2.metric("Median duration (yrs)", f"{clean['ProsecutionDuration'].median():.1f}")
    c3.metric("Mean duration (yrs)", f"{clean['ProsecutionDuration'].mean():.1f}")
    total_persons = int(df["TotalPersons"].sum()) if "TotalPersons" in df else 0
    c4.metric("Persons recorded", f"{total_persons:,}")

    st.divider()
    left, right = st.columns(2)

    with left:
        st.subheader("Prosecution duration distribution")
        fig = px.histogram(clean, x="ProsecutionDuration", nbins=int(clean["ProsecutionDuration"].max()) + 1)
        fig.update_layout(height=360, xaxis_title="Years to close", yaxis_title="Crime groups", margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Average duration by crime year")
        by_year = clean.groupby("CrimeYear")["ProsecutionDuration"].mean().reset_index()
        by_year = by_year[(by_year["CrimeYear"] >= 1990) & (by_year["CrimeYear"] <= 2025)]
        fig2 = px.line(by_year, x="CrimeYear", y="ProsecutionDuration", markers=True)
        fig2.update_layout(height=360, xaxis_title="Crime year", yaxis_title="Avg years to close", margin=dict(t=10))
        st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Raw prosecution table"):
        st.dataframe(df, use_container_width=True, hide_index=True)
