"""Entry point for the Slovenian crime-data dashboard.

Run with::

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make both `dashboard` and the seminar's `analysis` package importable.
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

st.set_page_config(
    page_title="SI Crime Explorer",
    page_icon="🇸🇮",
    layout="wide",
    initial_sidebar_state="expanded",
)

from dashboard.views import (  # noqa: E402  (import after sys.path setup)
    forecast,
    geography,
    immigration,
    overview,
    prediction,
    prosecution,
    trends,
    weather,
)

pages = [
    st.Page(overview.render, title="Overview", icon="🏠", url_path="overview", default=True),
    st.Page(trends.render, title="Historical Trends", icon="📈", url_path="trends"),
    st.Page(forecast.render, title="Forecast", icon="🔮", url_path="forecast"),
    st.Page(geography.render, title="Geography", icon="🗺️", url_path="geography"),
    st.Page(weather.render, title="Weather", icon="🌦️", url_path="weather"),
    st.Page(immigration.render, title="Immigration", icon="🛂", url_path="immigration"),
    st.Page(prediction.render, title="Crime Predictor", icon="🤖", url_path="prediction"),
    st.Page(prosecution.render, title="Prosecution", icon="⚖️", url_path="prosecution"),
]

with st.sidebar:
    st.markdown("### 🇸🇮 Crime Explorer")
    st.caption("FRI · Data Mining seminar")

st.navigation(pages).run()
