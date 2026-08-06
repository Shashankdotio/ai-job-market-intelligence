"""Overview page for the filtered AI job market."""

import pandas as pd
import streamlit as st

from dashboard.analytics import count_by_column, skill_frequency
from dashboard.components.charts import (
    BRAND_BLUE,
    BRAND_TEAL,
    BRAND_VIOLET,
    donut_chart,
    ranked_bar_chart,
)
from dashboard.components.layout import (
    format_timestamp,
    render_data_status,
    render_page_header,
)
from dashboard.components.tables import render_jobs_table
from dashboard.data_repository import GoldData


def render(data: GoldData, jobs: pd.DataFrame) -> None:
    """Render market-wide KPIs, rankings, and recently updated filtered jobs."""
    render_page_header(
        "AI Job Market Intelligence",
        "Explore current hiring demand across tracked AI employers.",
    )
    render_data_status(data.metadata)
    if jobs.empty:
        st.warning(
            "No jobs match the active filters. Clear or broaden them to continue."
        )
        return

    skills = skill_frequency(jobs)
    metrics = st.columns(5)
    metrics[0].metric("Open jobs", f"{len(jobs):,}")
    metrics[1].metric("Companies", f"{jobs['company'].nunique():,}")
    metrics[2].metric(
        "Locations",
        f"{jobs['location'].replace('', pd.NA).dropna().nunique():,}",
    )
    metrics[3].metric("Skills in demand", f"{len(skills):,}")
    metrics[4].metric("Last updated", format_timestamp(jobs["updated_at"].max()))

    left_column, right_column = st.columns(2)
    with left_column:
        st.plotly_chart(
            ranked_bar_chart(
                skills,
                label_column="skill",
                value_column="job_count",
                title="Most Requested Skills",
                color=BRAND_BLUE,
            ),
            use_container_width=True,
        )
    with right_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(jobs, "company"),
                label_column="company",
                value_column="job_count",
                title="Hiring Demand by Company",
                color=BRAND_VIOLET,
            ),
            use_container_width=True,
        )

    work_mode_column, role_column = st.columns((1, 1.4))
    with work_mode_column:
        st.plotly_chart(
            donut_chart(
                count_by_column(jobs, "work_mode"),
                label_column="work_mode",
                value_column="job_count",
                title="Work Arrangement",
            ),
            use_container_width=True,
        )
    with role_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(jobs, "title"),
                label_column="title",
                value_column="job_count",
                title="Most Common Roles",
                color=BRAND_TEAL,
                limit=8,
            ),
            use_container_width=True,
        )

    st.subheader("Recently Updated Jobs")
    render_jobs_table(
        jobs.sort_values("updated_at", ascending=False),
        empty_message="No job postings match the active filters.",
        max_rows=25,
    )
