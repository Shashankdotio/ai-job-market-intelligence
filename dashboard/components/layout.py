"""Page configuration and reusable presentation helpers."""

from datetime import datetime
from typing import Any

import streamlit as st


def configure_page() -> None:
    """Apply the application-wide Streamlit configuration and visual theme."""
    st.set_page_config(
        page_title="AI Job Market Intelligence",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
            .block-container {max-width: 1480px; padding-top: 1.75rem;}
            h1 {letter-spacing: -0.035em; padding-top: 0.25rem;}
            h2, h3 {letter-spacing: -0.02em;}
            [data-testid="stMetric"] {
                background: linear-gradient(145deg, #FFFFFF, #F8FAFC);
                border: 1px solid #E2E8F0;
                border-radius: 0.85rem;
                box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
                padding: 1rem;
            }
            [data-testid="stMetricLabel"] {font-size: 0.78rem; color: #475569;}
            [data-testid="stMetricValue"] {font-size: 1.55rem;}
            [data-testid="stSidebar"] {
                border-right: 1px solid #E2E8F0;
                background: #FAFCFF;
            }
            [data-testid="stSidebar"] .stButton button {border-radius: 0.5rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_data_status(metadata: dict[str, Any]) -> None:
    """Show the published gold snapshot identity and refresh timestamp."""
    generated_at = format_timestamp(metadata.get("generated_at"))
    snapshot_id = metadata.get("snapshot_id", "Unknown snapshot")
    st.caption(f"Gold snapshot: `{snapshot_id}` · Refreshed {generated_at}")


def render_page_header(title: str, description: str) -> None:
    """Render a consistent page title and concise analytical context."""
    st.title(title)
    st.caption(description)


def format_timestamp(value: object) -> str:
    """Format an ISO timestamp for a concise dashboard label."""
    if not value:
        return "Unknown"
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    return timestamp.strftime("%b %d, %Y %H:%M UTC")
