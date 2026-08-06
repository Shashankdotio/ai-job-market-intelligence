"""Company hiring drill-down page."""

import pandas as pd
import streamlit as st

from dashboard.analytics import count_by_column, skill_frequency
from dashboard.components.charts import BRAND_VIOLET, ranked_bar_chart
from dashboard.components.layout import (
    format_timestamp,
    render_data_status,
    render_page_header,
)
from dashboard.components.tables import render_jobs_table
from dashboard.data_repository import GoldData


def render(data: GoldData, jobs: pd.DataFrame) -> None:
    """Render company KPIs, skill distribution, and clickable job listings."""
    render_page_header(
        "Company Intelligence",
        "Compare demand signals and open roles for a selected employer.",
    )
    render_data_status(data.metadata)
    if jobs.empty:
        st.warning("No companies match the active filters.")
        return

    companies = count_by_column(jobs, "company")["company"].tolist()
    selected_company = st.selectbox("Company", companies)
    company_jobs = jobs.loc[jobs["company"] == selected_company].copy()
    company_skills = skill_frequency(company_jobs)
    metrics = st.columns(4)
    metrics[0].metric("Open jobs", f"{len(company_jobs):,}")
    metrics[1].metric(
        "Locations",
        f"{company_jobs['location'].replace('', pd.NA).dropna().nunique():,}",
    )
    metrics[2].metric("Skills requested", f"{len(company_skills):,}")
    metrics[3].metric(
        "Latest update",
        format_timestamp(company_jobs["updated_at"].max()),
    )

    chart_column, arrangement_column = st.columns((1.6, 1))
    with chart_column:
        st.plotly_chart(
            ranked_bar_chart(
                company_skills,
                label_column="skill",
                value_column="job_count",
                title=f"Skill Distribution · {selected_company}",
                color=BRAND_VIOLET,
                limit=15,
            ),
            use_container_width=True,
        )
    with arrangement_column:
        st.plotly_chart(
            ranked_bar_chart(
                count_by_column(company_jobs, "work_mode"),
                label_column="work_mode",
                value_column="job_count",
                title="Work Arrangement",
                color=BRAND_VIOLET,
                limit=3,
            ),
            use_container_width=True,
        )

    st.subheader(f"Open Jobs · {selected_company}")
    render_jobs_table(
        company_jobs.sort_values("updated_at", ascending=False),
        empty_message="No jobs match the active filters for this company.",
    )
