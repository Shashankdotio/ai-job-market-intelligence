"""Location and work-arrangement intelligence page."""

import pandas as pd
import streamlit as st

from dashboard.analytics import count_by_column
from dashboard.components.charts import BRAND_AMBER, donut_chart, ranked_bar_chart
from dashboard.components.layout import render_data_status, render_page_header
from dashboard.components.tables import render_jobs_table
from dashboard.data_repository import GoldData


def render(data: GoldData, jobs: pd.DataFrame) -> None:
    """Render location rankings, work-mode split, and location-specific jobs."""
    render_page_header(
        "Location Intelligence",
        "See where AI employers are hiring and how work arrangements differ.",
    )
    render_data_status(data.metadata)
    if jobs.empty:
        st.warning("No locations match the active filters.")
        return

    locations = count_by_column(jobs, "location", label="location")
    work_modes = count_by_column(jobs, "work_mode")

    st.subheader("Location overview")
    st.caption("Current hiring demand by geography and current work arrangement mix.")
    overview_columns = st.columns(3)
    overview_columns[0].metric(
        "Locations tracked",
        f"{len(locations):,}",
        help="Distinct locations represented in the filtered job set",
    )
    overview_columns[1].metric(
        "Top location",
        str(locations.iloc[0]["location"]),
        help="Most common location in the current filtered view",
    )
    overview_columns[2].metric(
        "Top location jobs",
        f"{int(locations.iloc[0]['job_count']):,}",
        help="Current role count in the leading location",
    )

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    left_column, right_column = st.columns((1.5, 1))
    with left_column:
        st.plotly_chart(
            ranked_bar_chart(
                locations,
                label_column="location",
                value_column="job_count",
                title="Top hiring locations",
                color=BRAND_AMBER,
                limit=20,
            ),
            use_container_width=True,
        )
    with right_column:
        if work_modes.empty:
            st.info("No work-arrangement data is available for the current filter set.")
        else:
            st.plotly_chart(
                donut_chart(
                    work_modes,
                    label_column="work_mode",
                    value_column="job_count",
                    title="Remote vs hybrid vs onsite",
                ),
                use_container_width=True,
            )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    selected_location = st.selectbox(
        "Jobs by location",
        locations["location"].tolist(),
    )
    location_jobs = jobs.loc[jobs["location"] == selected_location].copy()
    st.subheader(f"Location detail · {selected_location}")
    detail_columns = st.columns(3)
    detail_columns[0].metric(
        "Jobs in location",
        f"{len(location_jobs):,}",
        help="Jobs currently matching the selected location",
    )
    detail_columns[1].metric(
        "Employers",
        f"{location_jobs['company'].nunique():,}",
        help="Distinct companies hiring in this location",
    )
    detail_columns[2].metric(
        "Latest update",
        str(location_jobs["updated_at"].max())[:19] if not location_jobs.empty else "N/A",
        help="Most recent update among jobs in this location",
    )

    if location_jobs.empty:
        st.info("No jobs are currently available for the selected location in the active filter set.")
    else:
        render_jobs_table(
            location_jobs.sort_values("updated_at", ascending=False),
            empty_message="No jobs match this location.",
        )
