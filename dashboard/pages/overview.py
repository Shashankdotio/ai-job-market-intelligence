"""Overview page for the filtered AI job market."""

import pandas as pd
import plotly.graph_objects as go
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
from dashboard.data import load_historical_analytics_data
from dashboard.data_repository import GoldData


def _render_historical_line_chart(frame: pd.DataFrame, *, x_column: str, y_column: str, title: str, color: str) -> None:
    if frame.empty:
        st.info(f"No historical {title.lower()} data is available for the current gold snapshot.")
        return
    fig = go.Figure(
        go.Scatter(
            x=frame[x_column],
            y=frame[y_column],
            mode="lines+markers",
            line={"color": color, "width": 3},
            marker={"size": 8, "color": color},
            hovertemplate="%{x}<br>Jobs: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        height=340,
        margin={"l": 8, "r": 8, "t": 44, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"title": "Date" if x_column == "date" else "Week start"},
        yaxis={"title": "Discovered jobs"},
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_historical_bar_chart(frame: pd.DataFrame, *, x_column: str, y_column: str, title: str, color: str) -> None:
    if frame.empty:
        st.info(f"No historical {title.lower()} data is available for the current gold snapshot.")
        return
    fig = go.Figure(
        go.Bar(
            x=frame[x_column],
            y=frame[y_column],
            marker_color=color,
            hovertemplate="%{x}<br>Jobs: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        height=340,
        margin={"l": 8, "r": 8, "t": 44, "b": 8},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


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

    st.subheader("Historical hiring trends")
    st.caption("Discovery counts derived from historical Gold datasets; values are current snapshot dates, not live provider counts.")
    historical = load_historical_analytics_data()
    daily = historical.get("hiring_trends_daily", pd.DataFrame(columns=["date", "job_count"]))
    weekly = historical.get("hiring_trends_weekly", pd.DataFrame(columns=["week_start", "job_count"]))
    daily_column, weekly_column = st.columns(2)
    with daily_column:
        _render_historical_line_chart(daily, x_column="date", y_column="job_count", title="Daily job discoveries", color=BRAND_BLUE)
    with weekly_column:
        _render_historical_line_chart(weekly, x_column="week_start", y_column="job_count", title="Weekly job discoveries", color=BRAND_VIOLET)

    lifecycle = historical.get("lifecycle_summary", pd.DataFrame(columns=["metric", "value", "as_of"]))
    if not lifecycle.empty:
        st.subheader("Current lifecycle overview")
        st.caption("These metrics reflect current lifecycle state, not cumulative events.")
        life_values = {row["metric"]: int(row["value"]) for _, row in lifecycle.iterrows() if str(row.get("metric", "")).strip()}
        lifecycle_cols = st.columns(4)
        lifecycle_labels = ["Active", "Suspected closed", "Closed", "Reopened"]
        for idx, label in enumerate(lifecycle_labels):
            metric_name = ["active_jobs", "suspected_closed_jobs", "closed_jobs", "reopened_jobs"][idx]
            lifecycle_cols[idx].metric(label, f"{life_values.get(metric_name, 0):,}")
        st.info("Current lifecycle values are intentionally state-based and are not cumulative lifecycle event totals.")

    job_changes = historical.get("job_changes", pd.DataFrame(columns=["event_date", "update_count", "unique_jobs_updated"]))
    st.subheader("Meaningful job changes")
    if job_changes.empty:
        st.info("No historical posting update events are available for the current dataset.")
    else:
        _render_historical_bar_chart(job_changes, x_column="event_date", y_column="update_count", title="Posting update events by date", color=BRAND_TEAL)

    st.subheader("Recently Updated Jobs")
    render_jobs_table(
        jobs.sort_values("updated_at", ascending=False),
        empty_message="No job postings match the active filters.",
        max_rows=25,
    )
