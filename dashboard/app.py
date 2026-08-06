"""Streamlit entry point for the AI Job Market Intelligence Platform."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from dashboard.analytics import apply_filters, enrich_jobs
from dashboard.components.filters import render_global_filters, render_navigation
from dashboard.components.layout import configure_page
from dashboard.data import GOLD_DIRECTORY, load_dashboard_data
from dashboard.data_repository import GoldDataUnavailableError
from dashboard.pages import companies, locations, overview, roles, skills


PAGES = {
    "▦  Overview": overview.render,
    "▣  Companies": companies.render,
    "✦  Skills": skills.render,
    "⌖  Locations": locations.render,
    "≡  Roles": roles.render,
}


def main() -> None:
    """Configure the app, load gold data, and render the selected page."""
    configure_page()
    if st.sidebar.button("↻  Refresh published data", use_container_width=True):
        load_dashboard_data.clear()

    try:
        data = load_dashboard_data(str(GOLD_DIRECTORY))
    except GoldDataUnavailableError as error:
        st.title("AI Job Market Intelligence")
        st.info(str(error))
        st.code("python -m ai_job_market transform", language="bash")
        return

    jobs = enrich_jobs(data.job_postings)
    page_name = render_navigation()
    filters = render_global_filters(jobs)
    filtered_jobs = apply_filters(jobs, filters)
    st.sidebar.caption(f"{len(filtered_jobs):,} matching jobs")
    PAGES[page_name](data, filtered_jobs)


if __name__ == "__main__":
    main()
