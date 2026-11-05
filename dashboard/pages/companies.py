"""Company hiring drill-down page."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.analytics import count_by_column, skill_frequency
from dashboard.components.charts import BRAND_VIOLET, ranked_bar_chart
from dashboard.components.layout import (
    format_timestamp,
    render_data_status,
    render_page_header,
)
from dashboard.components.tables import render_jobs_table
from dashboard.data import load_historical_analytics_data
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

    historical = load_historical_analytics_data().get("company_activity", pd.DataFrame(columns=["company", "new_jobs", "closed_jobs", "reopened_jobs", "current_active_jobs", "current_suspected_closed_jobs"]))
    st.subheader("Historical company activity")
    if historical.empty:
        st.info("No historical company activity is available for the current gold snapshot.")
    else:
        company_activity = historical.loc[historical["company"] == selected_company]
        if company_activity.empty:
            st.info(f"No historical activity has been recorded for {selected_company}.")
        else:
            summary = company_activity.iloc[0].to_dict()
            metric_columns = st.columns(4)
            metric_columns[0].metric("New jobs", f"{int(summary.get('new_jobs', 0)):,}")
            metric_columns[1].metric("Closed jobs", f"{int(summary.get('closed_jobs', 0)):,}")
            metric_columns[2].metric("Reopened jobs", f"{int(summary.get('reopened_jobs', 0)):,}")
            metric_columns[3].metric("Current active jobs", f"{int(summary.get('current_active_jobs', 0)):,}")

            activity_chart = go.Figure()
            activity_chart.add_trace(go.Bar(x=["New jobs", "Closed jobs", "Reopened jobs", "Current active"], y=[int(summary.get("new_jobs", 0)), int(summary.get("closed_jobs", 0)), int(summary.get("reopened_jobs", 0)), int(summary.get("current_active_jobs", 0))], name=selected_company, marker_color=BRAND_VIOLET))
            activity_chart.update_layout(title=f"History for {selected_company}", height=340, margin={"l": 8, "r": 8, "t": 44, "b": 8}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(activity_chart, use_container_width=True)

    st.subheader(f"Open Jobs · {selected_company}")
    render_jobs_table(
        company_jobs.sort_values("updated_at", ascending=False),
        empty_message="No jobs match the active filters for this company.",
    )
