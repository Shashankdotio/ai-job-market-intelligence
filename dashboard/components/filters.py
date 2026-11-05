"""Sidebar navigation and globally shared dashboard filters."""

import streamlit as st

from dashboard.analytics import DashboardFilters, skill_frequency, unique_values


NAVIGATION = (
    "▦  Overview",
    "▣  Companies",
    "✦  Skills",
    "⌖  Locations",
    "≡  Roles",
    "◔  Market Intelligence",
)


def render_navigation() -> str:
    """Render the primary sidebar navigation with compact visual icons."""
    st.sidebar.markdown("### AI Job Market")
    st.sidebar.caption("Talent intelligence for AI hiring")
    return st.sidebar.radio("Navigate", NAVIGATION, label_visibility="collapsed")


def render_global_filters(jobs) -> DashboardFilters:
    """Render filter controls and return state used by every page."""
    with st.sidebar:
        st.divider()
        st.markdown("#### Global filters")
        companies = st.multiselect(
            "Company",
            options=unique_values(jobs, "company"),
            key="global_company_filter",
        )
        locations = st.multiselect(
            "Location",
            options=unique_values(jobs, "location"),
            key="global_location_filter",
        )
        skills = st.multiselect(
            "Skill",
            options=skill_frequency(jobs)["skill"].tolist(),
            key="global_skill_filter",
        )
        work_modes = st.multiselect(
            "Work arrangement",
            options=("Remote", "Hybrid", "Onsite"),
            key="global_work_mode_filter",
        )
        search_query = st.text_input(
            "Search jobs",
            placeholder="Title, company, skill…",
            key="global_search_filter",
        )
        if st.button("Clear filters", use_container_width=True):
            _clear_filter_state()
            st.rerun()

    return DashboardFilters(
        companies=tuple(companies),
        locations=tuple(locations),
        skills=tuple(skills),
        work_modes=tuple(work_modes),
        search_query=search_query,
    )


def _clear_filter_state() -> None:
    for key in (
        "global_company_filter",
        "global_location_filter",
        "global_skill_filter",
        "global_work_mode_filter",
        "global_search_filter",
    ):
        st.session_state.pop(key, None)
