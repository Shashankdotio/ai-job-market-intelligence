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

    st.subheader(f"{selected_company}")
    st.caption("Current filtered demand snapshot for the selected employer.")
    metrics = st.columns(4)
    metrics[0].metric(
        "Open jobs",
        f"{len(company_jobs):,}",
        help="Jobs currently matching the selected filters for this employer",
    )
    metrics[1].metric(
        "Locations",
        f"{company_jobs['location'].replace('', pd.NA).dropna().nunique():,}",
        help="Distinct locations across the filtered job set",
    )
    metrics[2].metric(
        "Skills requested",
        f"{len(company_skills):,}",
        help="Distinct skills requested by the employer in the filtered view",
    )
    metrics[3].metric(
        "Latest update",
        format_timestamp(company_jobs["updated_at"].max()),
        help="Most recent job update in the selected company's filtered jobs",
    )

    st.markdown("<div style='height: 0.75rem;'></div>", unsafe_allow_html=True)
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

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Historical company activity")
    st.caption("History is derived from lifecycle-aware Gold summaries; values are company-level totals, not live job counts.")
    historical = load_historical_analytics_data().get(
        "company_activity",
        pd.DataFrame(
            columns=[
                "company",
                "new_jobs",
                "closed_jobs",
                "reopened_jobs",
                "current_active_jobs",
                "current_suspected_closed_jobs",
            ]
        ),
    )

    if historical.empty:
        st.info(
            "No historical company activity is available for the current gold snapshot. "
            "This usually means the current dataset has not yet materialized lifecycle history."
        )
    else:
        company_activity = historical.loc[historical["company"] == selected_company]
        if company_activity.empty:
            st.info(f"No historical activity has been recorded for {selected_company}.")
        else:
            summary = company_activity.iloc[0].to_dict()
            metric_columns = st.columns(4)
            metric_columns[0].metric(
                "New jobs",
                f"{int(summary.get('new_jobs', 0)):,}",
                help="Jobs newly discovered for this company in the historical snapshot",
            )
            metric_columns[1].metric(
                "Closed jobs",
                f"{int(summary.get('closed_jobs', 0)):,}",
                help="Jobs closed at the company-level during historical evaluation",
            )
            metric_columns[2].metric(
                "Reopened jobs",
                f"{int(summary.get('reopened_jobs', 0)):,}",
                help="Jobs that returned to active after a closure",
            )
            metric_columns[3].metric(
                "Current active jobs",
                f"{int(summary.get('current_active_jobs', 0)):,}",
                help="Current active lifecycle count for this company",
            )

            history_chart = go.Figure()
            history_chart.add_trace(
                go.Bar(
                    x=["New jobs", "Closed jobs", "Reopened jobs", "Current active"],
                    y=[
                        int(summary.get("new_jobs", 0)),
                        int(summary.get("closed_jobs", 0)),
                        int(summary.get("reopened_jobs", 0)),
                        int(summary.get("current_active_jobs", 0)),
                    ],
                    name=selected_company,
                    marker_color=BRAND_VIOLET,
                    hovertemplate="%{x}<br>Jobs: %{y}<extra></extra>",
                )
            )
            history_chart.update_layout(
                title=f"Historical activity for {selected_company}",
                height=340,
                margin={"l": 8, "r": 8, "t": 44, "b": 8},
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis={"title": "Metric"},
                yaxis={"title": "Job count"},
            )
            st.plotly_chart(history_chart, use_container_width=True)

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader(f"Open Jobs · {selected_company}")
    render_jobs_table(
        company_jobs.sort_values("updated_at", ascending=False),
        empty_message="No jobs match the active filters for this company.",
    )
