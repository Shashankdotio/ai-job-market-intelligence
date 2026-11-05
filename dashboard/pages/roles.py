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

    st.subheader("Role overview")
    st.caption("Current role mix across the filtered hiring market.")
    overview_columns = st.columns(4)
    overview_columns[0].metric(
        "Role titles",
        f"{jobs['title'].nunique():,}",
        help="Distinct job titles in the filtered dataset",
    )
    overview_columns[1].metric(
        "Departments",
        f"{jobs['department'].replace('', pd.NA).dropna().nunique():,}",
        help="Distinct departments represented in the current job window",
    )
    overview_columns[2].metric(
        "Most common title",
        str(count_by_column(jobs, "title").iloc[0]["title"]),
        help="Most frequent job title in the current filter set",
    )
    overview_columns[3].metric(
        "Top title count",
        f"{int(count_by_column(jobs, 'title').iloc[0]['job_count']):,}",
        help="Number of jobs matching the leading title",
    )

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    title_column, department_column = st.columns(2)
    with title_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(jobs, "title"),
                label_column="title",
                value_column="job_count",
                title="Most common job titles",
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
                title="Hiring by department",
                color=BRAND_TEAL,
                limit=15,
            ),
            use_container_width=True,
        )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    seniority_column, spacer_column = st.columns((1, 1))
    with seniority_column:
        seniority_counts = count_by_column(jobs, "seniority")
        if seniority_counts.empty:
            st.info("No seniority data is available for the current filter set.")
        else:
            st.plotly_chart(
                donut_chart(
                    seniority_counts,
                    label_column="seniority",
                    value_column="job_count",
                    title="Seniority distribution",
                ),
                use_container_width=True,
            )
    with spacer_column:
        employers = count_by_column(jobs, "company")
        if employers.empty:
            st.info("No employer breakdown is available for the current filter set.")
        else:
            st.plotly_chart(
                ranked_bar_chart(
                    employers,
                    label_column="company",
                    value_column="job_count",
                    title="Companies hiring for these roles",
                    color=BRAND_VIOLET,
                    limit=8,
                ),
                use_container_width=True,
            )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Searchable jobs")
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
    if table_jobs.empty:
        st.info("No jobs match that role search in the current filter set.")
    else:
        render_jobs_table(
            table_jobs.sort_values("updated_at", ascending=False),
            empty_message="No jobs match that role search.",
        )
