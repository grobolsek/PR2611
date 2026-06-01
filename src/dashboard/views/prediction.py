"""Interactive Random-Forest crime predictor, reusing analysis.crime_prediction."""

from __future__ import annotations

import re

import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from analysis.crime_prediction import prepare_advanced_dataset
from dashboard import data

FEATURE_COLS = ["Hour", "Day_Encoded", "Location_Encoded", "Izdana_Dovoljenja_Mesec"]


def _start_hour(ura: object) -> int:
    if pd.isna(ura):
        return 12
    m = re.match(r"^(\d{1,2})", str(ura).strip())
    return int(m.group(1)) if m else 12


@st.cache_resource(show_spinner="Training Random-Forest models…")
def train_models(year: int) -> dict[str, object]:
    """Train the probability + crime-type models for a given year."""
    crimes = data.load_formatted(
        year,
        columns=("UraStoritve", data.MONTH_COL, "DanVTednu", data.LOCATION_COL, data.CRIME_GROUP_COL),
    )
    if crimes.empty:
        return {}
    # Make the hour feature meaningful: parse "HH:MM-HH:MM" to a start hour.
    crimes = crimes.copy()
    crimes["UraStoritve"] = crimes["UraStoritve"].apply(_start_hour)

    imm = data.load_immigration()
    dataset, encoders = prepare_advanced_dataset(crimes, imm)

    X = dataset[FEATURE_COLS]
    y_prob = dataset["Crime_Occurred"]
    Xp_tr, Xp_te, yp_tr, yp_te = train_test_split(X, y_prob, test_size=0.2, random_state=42)
    model_prob = RandomForestClassifier(n_estimators=100, min_samples_leaf=5, random_state=42)
    model_prob.fit(Xp_tr, yp_tr)

    real = dataset[dataset["Crime_Occurred"] == 1].copy()
    le_type = LabelEncoder()
    real["KD_Encoded"] = le_type.fit_transform(real[data.CRIME_GROUP_COL].astype(str))
    Xt_tr, Xt_te, yt_tr, yt_te = train_test_split(real[FEATURE_COLS], real["KD_Encoded"], test_size=0.2, random_state=42)
    model_type = RandomForestClassifier(n_estimators=100, min_samples_leaf=3, random_state=42)
    model_type.fit(Xt_tr, yt_tr)

    return {
        "model_prob": model_prob,
        "model_type": model_type,
        "encoders": encoders,
        "le_type": le_type,
        "prob_acc": model_prob.score(Xp_te, yp_te),
        "type_acc": model_type.score(Xt_te, yt_te),
        "days": list(encoders["Day"].classes_),
        "locations": list(encoders["Location"].classes_),
    }


def render() -> None:
    st.title("🤖 Crime Predictor")
    st.caption(
        "Two Random-Forest models from `analysis.crime_prediction`: one estimates the "
        "probability that a crime occurs, the other its most likely cluster.",
    )

    years = data.formatted_years()
    if not years:
        st.warning("No formatted crime files found.")
        return

    year = st.selectbox("Train on year", years[::-1])
    models = train_models(year)
    if not models:
        st.error("Could not train models for this year.")
        return

    c1, c2 = st.columns(2)
    c1.metric("Occurrence model accuracy", f"{models['prob_acc'] * 100:.1f}%")
    c2.metric("Type model accuracy", f"{models['type_acc'] * 100:.1f}%")

    st.divider()
    st.subheader("Try a scenario")
    a, b = st.columns(2)
    hour = a.slider("Hour of day", 0, 23, 10)
    day = a.selectbox("Day of week", models["days"])
    location = b.selectbox("Police directorate", models["locations"])
    immigration = b.slider("Monthly issued permits", 0, 12000, 7000, step=250)

    if st.button("Predict", type="primary", width='stretch'):
        day_enc = models["encoders"]["Day"].transform([day])[0]
        loc_enc = models["encoders"]["Location"].transform([location])[0]
        x = pd.DataFrame([[hour, day_enc, loc_enc, immigration]], columns=FEATURE_COLS)

        prob = models["model_prob"].predict_proba(x)[0][1] * 100
        type_enc = models["model_type"].predict(x)
        type_name = models["le_type"].inverse_transform(type_enc)[0]

        r1, r2 = st.columns(2)
        r1.metric("Crime probability", f"{prob:.1f}%")
        r2.metric("Most likely cluster", type_name)

        proba = models["model_type"].predict_proba(x)[0]
        top = (
            pd.DataFrame({"cluster": models["le_type"].classes_, "probability": proba}).sort_values("probability", ascending=False).head(8)
        )
        fig = px.bar(
            top,
            x="probability",
            y="cluster",
            orientation="h",
            labels={"probability": "Probability", "cluster": ""},
        )
        fig.update_layout(height=360, yaxis=dict(categoryorder="total ascending"), margin=dict(t=10))
        st.plotly_chart(fig, width='stretch')

    st.divider()
    st.subheader("What drives the occurrence model?")
    importances = pd.DataFrame({"feature": FEATURE_COLS, "importance": models["model_prob"].feature_importances_}).sort_values(
        "importance", ascending=False
    )
    fig_i = px.bar(importances, x="importance", y="feature", orientation="h")
    fig_i.update_layout(height=260, yaxis=dict(categoryorder="total ascending"), margin=dict(t=10))
    st.plotly_chart(fig_i, width='stretch')
