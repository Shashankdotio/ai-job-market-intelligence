"""Role, department, and seniority intelligence page."""

import pandas as pd
import streamlit as st

from dashboard.analytics import count_by_column
from dashboard.components.charts import (
    BRAND_BLUE,
    BRAND_TEAL,
    BRAND_VIOLET,
    donut_chart,
    ranked_bar_chart,
)
from dashboard.components.layout import render_data_status, render_page_header
from dashboard.components.tables import render_jobs_table
from dashboard.data_repository import GoldData


def render(data: GoldData, jobs: pd.DataFrame) -> None:
    """Render title, department, seniority, and searchable-job insights."""
    render_page_header(
        "Role Intelligence",
        "Explore the role mix, organizations, and seniority behind hiring demand.",
    )
    render_data_status(data.metadata)
    if jobs.empty:
        st.warning("No roles match the active filters.")
        return

    title_column, department_column = st.columns(2)
    with title_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(jobs, "title"),
                label_column="title",
                value_column="job_count",
                title="Most Common Job Titles",
                color=BRAND_BLUE,
                limit=15,
            ),
            use_container_width=True,
        )
    with department_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(jobs, "department"),
                label_column="department",
                value_column="job_count",
                title="Hiring by Department",
                color=BRAND_TEAL,
                limit=15,
            ),
            use_container_width=True,
        )

    seniority_column, spacer_column = st.columns((1, 1))
    with seniority_column:
        st.plotly_chart(
            donut_chart(
                count_by_column(jobs, "seniority"),
                label_column="seniority",
                value_column="job_count",
                title="Seniority Distribution",
            ),
            use_container_width=True,
        )
    with spacer_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(jobs, "company"),
                label_column="company",
                value_column="job_count",
                title="Companies Hiring for These Roles",
                color=BRAND_VIOLET,
                limit=8,
            ),
            use_container_width=True,
        )

    st.subheader("Searchable Jobs")
    role_query = st.text_input(
        "Search within these jobs",
        placeholder="Engineer, manager…",
    )
    table_jobs = jobs
    if role_query:
        table_jobs = jobs.loc[
            jobs["title"].str.contains(role_query, case=False, na=False, regex=False)
            | jobs["department"].str.contains(
                role_query,
                case=False,
                na=False,
                regex=False,
            )
        ]
    render_jobs_table(
        table_jobs.sort_values("updated_at", ascending=False),
        empty_message="No jobs match that role search.",
    )
