"""Skills demand and employer comparison page."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.analytics import (
    company_skill_frequency,
    jobs_with_skill,
    skill_frequency,
)
from dashboard.components.charts import BRAND_BLUE, BRAND_TEAL, ranked_bar_chart
from dashboard.components.layout import render_data_status, render_page_header
from dashboard.components.tables import render_jobs_table
from dashboard.data import load_historical_analytics_data
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

    st.subheader("Skill demand overview")
    st.caption("Skill counts reflect the current filtered job market snapshot.")
    overview_columns = st.columns(3)
    overview_columns[0].metric(
        "Skills tracked",
        f"{len(skills):,}",
        help="Unique skill labels in the current filtered view",
    )
    overview_columns[1].metric(
        "Top skill",
        str(skills.iloc[0]["skill"]),
        help="Most frequently requested skill in the current filtered view",
    )
    overview_columns[2].metric(
        "Top skill count",
        f"{int(skills.iloc[0]['job_count']):,}",
        help="Number of current jobs requesting the leading skill",
    )

    query = st.text_input("Search skills", placeholder="Python, AWS, LLM…")
    matching_skills = skills.loc[
        skills["skill"].str.contains(query, case=False, na=False, regex=False)
        if query
        else pd.Series(True, index=skills.index)
    ]
    if matching_skills.empty:
        st.info("No skills match that search. Try a broader term.")
        return

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    chart_column, detail_column = st.columns((1.4, 1))
    with chart_column:
        st.plotly_chart(
            ranked_bar_chart(
                matching_skills,
                label_column="skill",
                value_column="job_count",
                title="Most demanded skills",
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
        st.metric("Matching jobs", f"{len(selected_skill_jobs):,}", help="Jobs currently requesting the selected skill")
        st.metric(
            "Companies requesting it",
            f"{selected_skill_jobs['company'].nunique():,}",
            help="Distinct employers requesting this skill in the filtered view",
        )

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    st.subheader("Company demand for this skill")
    company_skill_counts = company_skill_frequency(jobs)
    requesting_companies = company_skill_counts.loc[
        company_skill_counts["skill"] == selected_skill
    ]
    if requesting_companies.empty:
        st.info(f"No companies currently request {selected_skill} in the active filter set.")
    else:
        st.plotly_chart(
            ranked_bar_chart(
                requesting_companies,
                label_column="company",
                value_column="job_count",
                title=f"Companies requesting {selected_skill}",
                color=BRAND_TEAL,
                limit=15,
            ),
            use_container_width=True,
        )

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
    st.subheader(f"Jobs requesting {selected_skill}")
    render_jobs_table(
        selected_skill_jobs.sort_values("updated_at", ascending=False),
        empty_message="No matching jobs are available.",
    )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Historical skill trends")
    historical_skill_data = load_historical_analytics_data().get(
        "skill_demand_trends",
        pd.DataFrame(columns=["date", "skill", "job_count"]),
    )
    if historical_skill_data.empty:
        st.info(
            "Historical skill trends are unavailable because the repository does not currently contain reliable historical skill observations. "
            "The current dashboard intentionally does not infer or fabricate past skill demand."
        )
    else:
        chart_data = historical_skill_data.sort_values(["date", "job_count"], ascending=[True, False])
        fig = go.Figure(
            go.Bar(
                x=chart_data["skill"],
                y=chart_data["job_count"],
                marker_color=BRAND_BLUE,
                hovertemplate="%{x}<br>Jobs: %{y}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Historical skill demand when available",
            xaxis_title="Skill",
            yaxis_title="Job count",
            height=340,
            margin={"l": 8, "r": 8, "t": 52, "b": 8},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
