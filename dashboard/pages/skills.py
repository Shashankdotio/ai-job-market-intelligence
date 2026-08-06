"""Skills demand and employer comparison page."""

import pandas as pd
import streamlit as st

from dashboard.analytics import (
    company_skill_frequency,
    jobs_with_skill,
    skill_frequency,
)
from dashboard.components.charts import BRAND_BLUE, BRAND_TEAL, ranked_bar_chart
from dashboard.components.layout import render_data_status, render_page_header
from dashboard.components.tables import render_jobs_table
from dashboard.data_repository import GoldData


def render(data: GoldData, jobs: pd.DataFrame) -> None:
    """Render searchable skill demand, company demand, and related jobs."""
    render_page_header(
        "Skills Intelligence",
        "Identify high-demand skills and the employers requesting them.",
    )
    render_data_status(data.metadata)
    skills = skill_frequency(jobs)
    if skills.empty:
        st.warning("No skills are available for the active filters.")
        return

    query = st.text_input("Search skills", placeholder="Python, AWS, LLM…")
    matching_skills = skills.loc[
        skills["skill"].str.contains(query, case=False, na=False, regex=False)
        if query
        else pd.Series(True, index=skills.index)
    ]
    if matching_skills.empty:
        st.info("No skills match that search. Try a broader term.")
        return

    chart_column, detail_column = st.columns((1.4, 1))
    with chart_column:
        st.plotly_chart(
            ranked_bar_chart(
                matching_skills,
                label_column="skill",
                value_column="job_count",
                title="Skill Frequency Across Matching Jobs",
                color=BRAND_BLUE,
                limit=20,
            ),
            use_container_width=True,
        )
    with detail_column:
        selected_skill = st.selectbox(
            "Explore a skill",
            matching_skills["skill"].tolist(),
        )
        selected_skill_jobs = jobs_with_skill(jobs, selected_skill)
        st.metric("Matching jobs", f"{len(selected_skill_jobs):,}")
        st.metric(
            "Companies requesting it",
            f"{selected_skill_jobs['company'].nunique():,}",
        )

    company_skill_counts = company_skill_frequency(jobs)
    requesting_companies = company_skill_counts.loc[
        company_skill_counts["skill"] == selected_skill
    ]
    st.plotly_chart(
        ranked_bar_chart(
            requesting_companies,
            label_column="company",
            value_column="job_count",
            title=f"Companies Requesting {selected_skill}",
            color=BRAND_TEAL,
            limit=15,
        ),
        use_container_width=True,
    )
    st.subheader(f"Jobs Requesting {selected_skill}")
    render_jobs_table(
        selected_skill_jobs.sort_values("updated_at", ascending=False),
        empty_message="No matching jobs are available.",
    )
