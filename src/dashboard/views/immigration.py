"""Crime ⇄ immigration correlation, reusing analysis.monthly_crime_immigration_corr."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis import monthly_crime_immigration_corr as mci
from dashboard import data


def render() -> None:
    st.title("🛂 Immigration Correlation")
    st.caption(
        "Do monthly issued residence permits move with recorded crime? Correlation via `analysis.monthly_crime_immigration_corr`.",
    )

    imm = data.load_immigration()
    if imm.empty:
        st.warning("No immigration data found.")
        return

    st.subheader("Monthly issued residence permits")
    fig_imm = px.area(imm, x="Datum", y="Izdana_Dovoljenja_Mesec", labels={"Izdana_Dovoljenja_Mesec": "Permits"})
    fig_imm.update_layout(height=300, margin=dict(t=10), xaxis_title="")
    st.plotly_chart(fig_imm, width='stretch')

    st.divider()

    imm_years = sorted({int(d.year) for d in imm["Datum"].dropna()})
    crime_years = data.formatted_years()
    common = [y for y in crime_years if y in imm_years]
    if not common:
        st.warning("No year overlaps between crime and immigration data.")
        return

    col_y, col_c = st.columns(2)
    year = col_y.selectbox("Year", common[::-1])

    corrs = data.immigration_cluster_correlations(year)
    if not corrs.empty:
        options = list(corrs.index)

        def _fmt(label: str) -> str:
            return f"{label}  (r={corrs[label]:+.2f})"
    else:
        crimes_for_clusters = data.load_formatted(year, columns=(data.CRIME_GROUP_COL,))
        clusters = sorted(crimes_for_clusters[data.CRIME_GROUP_COL].dropna().unique())
        options = [data.ALL_CRIMES_LABEL, *clusters]

        def _fmt(label: str) -> str:
            return label

    cluster = col_c.selectbox("Crime cluster (sorted by |correlation|)", options, format_func=_fmt)
    crime_cluster = None if cluster == data.ALL_CRIMES_LABEL else cluster

    corr = mci.analyze_monthly_correlation(year, data.BASE_DIR, crime_cluster)
    if corr.empty:
        st.warning("No overlapping monthly data for this selection.")
        return

    coef = corr.loc["crime_count", "Izdana_Dovoljenja_Mesec"]
    st.metric(f"Pearson r — {cluster} vs permits ({year})", f"{coef:.3f}")

    # Rebuild the merged monthly series for a dual-axis chart.
    crime_monthly = mci.get_monthly_crime_counts(
        data.load_formatted(year, columns=(data.CRIME_GROUP_COL, data.MONTH_COL)),
        crime_cluster,
    )
    crime_monthly[data.MONTH_COL] = (
        crime_monthly[data.MONTH_COL]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .apply(lambda x: f"0{x}" if len(x) == 6 else x)
    )
    imm_y = imm.copy()
    imm_y[data.MONTH_COL] = imm_y[data.MONTH_COL].apply(lambda x: f"0{x}" if len(x) == 6 else x)
    merged = crime_monthly.merge(imm_y, on=data.MONTH_COL, how="inner").sort_values("Datum")

    if not merged.empty:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Scatter(x=merged["Datum"], y=merged["crime_count"], name=cluster, line=dict(color="crimson")),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=merged["Datum"], y=merged["Izdana_Dovoljenja_Mesec"], name="Permits", line=dict(color="royalblue")),
            secondary_y=True,
        )
        fig.update_yaxes(title_text="Monthly crime count", secondary_y=False)
        fig.update_yaxes(title_text="Issued permits", secondary_y=True)
        fig.update_layout(height=440, legend=dict(orientation="h", y=1.02, yanchor="bottom"), margin=dict(t=10))
        st.plotly_chart(fig, width='stretch')

    st.dataframe(
        corr.style.background_gradient(cmap="RdBu", vmin=-1, vmax=1).format("{:.3f}"),
        width='stretch',
    )
