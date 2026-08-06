"""Cached Streamlit access to the dashboard's read-only gold repository."""

from pathlib import Path

import streamlit as st

from dashboard.data_repository import GoldData, load_gold_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIRECTORY = PROJECT_ROOT / "data" / "gold"


@st.cache_data(ttl=300, show_spinner="Loading market intelligence data...")
def load_dashboard_data(gold_directory: str) -> GoldData:
    """Load gold artifacts with a short cache suitable for scheduled refreshes."""
    return load_gold_data(Path(gold_directory))
