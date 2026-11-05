"""Market-intelligence dashboard page for hiring momentum and role/skill movement."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.charts import BRAND_AMBER, BRAND_BLUE, BRAND_TEAL, BRAND_VIOLET
from dashboard.components.layout import render_data_status, render_page_header
from dashboard.data import load_market_intelligence_data
from dashboard.data_repository import GoldData


def _render_line_chart(frame: pd.DataFrame, *, x_column: str, y_column: str, title: str, color: str) -> None:
    if frame.empty:
        st.info(
            "Historical market intelligence is unavailable for the current Gold snapshot. "
            "This page will show clear empty states until trusted historical data exists."
        )
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
        xaxis_title="Period",
        yaxis_title="Active jobs",
        height=340,
        margin={"l": 10, "r": 10, "t": 48, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_company_delta_chart(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.info("No company movement is available because the relevant historical comparison window is empty.")
        return
    chart_data = frame.copy()
    chart_data["delta_color"] = chart_data["delta_active_jobs"].apply(lambda value: BRAND_TEAL if value >= 0 else BRAND_AMBER)
    fig = go.Figure(
        go.Bar(
            x=chart_data["delta_active_jobs"],
            y=chart_data["company"],
            orientation="h",
            marker_color=chart_data["delta_color"],
            hovertemplate="%{y}<br>Delta: %{x}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Company activity movement",
        xaxis_title="Change in active jobs",
        yaxis_title="Company",
        height=max(320, len(chart_data) * 28),
        margin={"l": 10, "r": 10, "t": 48, "b": 10},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def render(data: GoldData, jobs: pd.DataFrame) -> None:
    """Render hiring momentum, company movement, role demand, and skill momentum."""
    render_page_header(
        "Market Intelligence",
        "Track hiring momentum across companies, roles, and skill demand using historical data only.",
    )
    render_data_status(data.metadata)

    market = load_market_intelligence_data()
    daily = market.get("daily", pd.DataFrame(columns=["date", "active_jobs", "previous_period_active_jobs", "delta_active_jobs", "delta_pct", "sample_size"]))
    weekly = market.get("weekly", pd.DataFrame(columns=["week_start", "active_jobs", "previous_period_active_jobs", "delta_active_jobs", "delta_pct", "sample_size"]))
    company_movement = market.get("company_movement", pd.DataFrame(columns=["company", "current_active_jobs", "previous_period_active_jobs", "delta_active_jobs", "delta_pct", "status", "sample_size"]))
    role_hiring = market.get("role_hiring_trends", pd.DataFrame(columns=["date", "role", "role_count", "previous_period_role_count", "delta_count", "delta_pct", "sample_size"]))
    skill_momentum = market.get("skill_momentum", pd.DataFrame(columns=["skill", "current_period_jobs", "previous_period_jobs", "delta_jobs", "delta_pct", "sample_size", "coverage_pct", "status"]))
    if daily.empty and weekly.empty and company_movement.empty and role_hiring.empty and skill_momentum.empty:
        st.info(
            "No reliable historical market-intelligence signals are available yet. "
            "The dashboard intentionally keeps this section empty and transparent until there is enough trustworthy history."
        )
        return

    metrics_columns = st.columns(4)
    if not daily.empty:
        latest_daily = daily.iloc[-1]
        metrics_columns[0].metric(
            "Latest active jobs",
            f"{int(latest_daily['active_jobs']):,}",
            delta=f"{int(latest_daily['delta_active_jobs']):+,}",
            help="Daily active jobs versus the previous period in the current history window.",
        )
    else:
        metrics_columns[0].metric("Latest active jobs", "n/a", help="No daily active-job history is available.")

    if not company_movement.empty:
        increase_count = int((company_movement["status"] == "increasing").sum())
        decrease_count = int((company_movement["status"] == "decreasing").sum())
        metrics_columns[1].metric("Companies rising", f"{increase_count:,}", help="Companies with increasing active-job counts in the latest comparison window.")
        metrics_columns[2].metric("Companies falling", f"{decrease_count:,}", help="Companies with decreasing active-job counts in the latest comparison window.")
    else:
        metrics_columns[1].metric("Companies rising", "0", help="No reliable company movement data is available.")
        metrics_columns[2].metric("Companies falling", "0", help="No reliable company movement data is available.")

    if not skill_momentum.empty:
        rising_skills = int((skill_momentum["status"] == "increasing").sum())
        metrics_columns[3].metric("Skill momentum signals", f"{rising_skills:,}", help="Skills whose demand increased versus the previous equivalent period.")
    else:
        metrics_columns[3].metric("Skill momentum signals", "0", help="No reliable skill-history comparison is available.")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Active hiring trend")
    daily_col, weekly_col = st.columns(2)
    with daily_col:
        _render_line_chart(daily, x_column="date", y_column="active_jobs", title="Daily active job postings", color=BRAND_BLUE)
    with weekly_col:
        _render_line_chart(weekly, x_column="week_start", y_column="active_jobs", title="Weekly active job postings", color=BRAND_VIOLET)

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Company movement")
    if company_movement.empty:
        st.info("No company-level movement can be shown with the current history. This is expected when the dataset is too sparse.")
    else:
        top_movers = company_movement.sort_values(["delta_active_jobs", "company"], ascending=[False, True], kind="mergesort").head(12)
        _render_company_delta_chart(top_movers)
        st.dataframe(
            top_movers[["company", "current_active_jobs", "previous_period_active_jobs", "delta_active_jobs", "delta_pct", "status"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Role demand trend")
    if role_hiring.empty:
        st.info("Role-hiring trend data is unavailable because there are not enough historical title observations to compare periods reliably.")
    else:
        latest_role_date = role_hiring["date"].max()
        latest_roles = role_hiring.loc[role_hiring["date"] == latest_role_date].copy()
        latest_roles = latest_roles.sort_values(["role_count", "role"], ascending=[False, True], kind="mergesort").head(10)
        fig = go.Figure(
            go.Bar(
                x=latest_roles["role_count"],
                y=latest_roles["role"],
                orientation="h",
                marker_color=BRAND_TEAL,
                hovertemplate="%{y}<br>Jobs: %{x}<extra></extra>",
            )
        )
        fig.update_layout(
            title=f"Role demand on {latest_role_date}",
            xaxis_title="Jobs",
            yaxis_title="Role",
            height=max(320, len(latest_roles) * 28),
            margin={"l": 10, "r": 10, "t": 48, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            latest_roles[["role", "role_count", "previous_period_role_count", "delta_count", "delta_pct"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    st.subheader("Skill momentum")
    if skill_momentum.empty:
        st.info(
            "Historical skill-demand momentum is unavailable because the repository does not currently include reliable historical skill observations for a comparable period. "
            "The current dashboard intentionally does not infer or fabricate momentum."
        )
    else:
        momentum = skill_momentum.sort_values(["delta_jobs", "skill"], ascending=[False, True], kind="mergesort").head(12)
        fig = go.Figure(
            go.Bar(
                x=momentum["delta_jobs"],
                y=momentum["skill"],
                orientation="h",
                marker_color=[BRAND_VIOLET if value >= 0 else BRAND_AMBER for value in momentum["delta_jobs"]],
                hovertemplate="%{y}<br>Delta: %{x}<extra></extra>",
            )
        )
        fig.update_layout(
            title="Skill demand momentum",
            xaxis_title="Change in jobs",
            yaxis_title="Skill",
            height=max(320, len(momentum) * 28),
            margin={"l": 10, "r": 10, "t": 48, "b": 10},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            momentum[["skill", "current_period_jobs", "previous_period_jobs", "delta_jobs", "delta_pct", "coverage_pct", "status"]],
            use_container_width=True,
            hide_index=True,
        )
