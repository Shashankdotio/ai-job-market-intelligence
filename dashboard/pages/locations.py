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
    left_column, right_column = st.columns((1.5, 1))
    with left_column:
        st.plotly_chart(
            ranked_bar_chart(
                locations,
                label_column="location",
                value_column="job_count",
                title="Top Hiring Locations",
                color=BRAND_AMBER,
                limit=20,
            ),
            use_container_width=True,
        )
    with right_column:
        st.plotly_chart(
            donut_chart(
                work_modes,
                label_column="work_mode",
                value_column="job_count",
                title="Remote vs Hybrid vs Onsite",
            ),
            use_container_width=True,
        )

    selected_location = st.selectbox("Jobs by location", locations["location"].tolist())
    location_jobs = jobs.loc[jobs["location"] == selected_location]
    st.subheader(f"Open Jobs · {selected_location}")
    render_jobs_table(
        location_jobs.sort_values("updated_at", ascending=False),
        empty_message="No jobs match this location.",
    )
