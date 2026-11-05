"""Skills demand and employer comparison page."""

import json

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
from dashboard.data import load_historical_analytics_data, load_skill_cooccurrence_data
from dashboard.data_repository import GoldData


def _parse_skill_values(raw_value: object) -> list[str]:
    """Normalize raw skill payloads into a deduplicated list of labels."""
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        values = raw_value
    elif isinstance(raw_value, tuple):
        values = list(raw_value)
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            values = [text]
        else:
            if isinstance(parsed, list):
                values = parsed
            elif isinstance(parsed, str):
                values = [parsed]
            else:
                values = []
    else:
        values = [raw_value]

    parsed_skills: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        parsed_skills.append(text)
    return parsed_skills


def _skill_pair_coverage_summary(jobs: pd.DataFrame) -> tuple[int, int, float]:
    """Return total postings, postings with usable skills, and coverage percentage."""
    total_postings = len(jobs)
    usable_postings = 0
    for raw_skill_value in jobs.get("skills", pd.Series([], index=jobs.index)).tolist():
        if _parse_skill_values(raw_skill_value):
            usable_postings += 1
    coverage_pct = (usable_postings / total_postings * 100.0) if total_postings else 0.0
    return total_postings, usable_postings, coverage_pct


def filter_skill_pairs(
    pairs: pd.DataFrame,
    *,
    min_threshold: int = 2,
    selected_skill: str | None = None,
) -> pd.DataFrame:
    """Apply client-side filters to the co-occurrence dataset."""
    if pairs.empty:
        return pairs.copy()

    filtered = pairs.copy()
    filtered["pair_count"] = pd.to_numeric(filtered["pair_count"], errors="coerce").fillna(0)
    filtered = filtered[filtered["pair_count"] >= min_threshold].copy()

    if selected_skill:
        skill_key = str(selected_skill).strip()
        if skill_key:
            filtered = filtered[
                filtered["skill_a"].astype(str).str.casefold().eq(skill_key.casefold())
                | filtered["skill_b"].astype(str).str.casefold().eq(skill_key.casefold())
            ].copy()

    return filtered.sort_values(
        ["pair_count", "skill_a", "skill_b"],
        ascending=[False, True, True],
        kind="mergesort",
    )


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
    st.subheader("Skill combinations")
    st.caption(
        "Pair metrics come from the published Gold co-occurrence outputs. "
        "P(B | A) is directional; P(A | B) is the reverse direction; Jaccard similarity is symmetric."
    )
    cooccurrence_data = load_skill_cooccurrence_data()
    overall_pairs = cooccurrence_data.get("overall", pd.DataFrame(columns=[
        "skill_a",
        "skill_b",
        "pair_count",
        "skill_a_count",
        "skill_b_count",
        "pct_b_given_a",
        "pct_a_given_b",
        "jaccard_similarity",
    ]))
    company_pairs = cooccurrence_data.get("by_company", pd.DataFrame(columns=[
        "company",
        "skill_a",
        "skill_b",
        "pair_count",
        "skill_a_count",
        "skill_b_count",
        "pct_b_given_a",
        "pct_a_given_b",
        "jaccard_similarity",
    ]))

    total_postings, usable_postings, coverage_pct = _skill_pair_coverage_summary(jobs)
    coverage_columns = st.columns(3)
    coverage_columns[0].metric("Postings", f"{total_postings:,}", help="Total filtered job postings in the current Gold market snapshot.")
    coverage_columns[1].metric("With usable skill data", f"{usable_postings:,}", help="Postings with at least one valid skill label after normalization.")
    coverage_columns[2].metric("Skill coverage", f"{coverage_pct:.1f}%", help="Share of postings with usable skill data; used for co-occurrence coverage context.")

    pair_threshold = st.slider(
        "Minimum co-occurrence threshold",
        min_value=1,
        max_value=max(10, int(overall_pairs["pair_count"].max()) if not overall_pairs.empty else 10),
        value=2,
        step=1,
        help="Only show pairs observed at least this many times in the current Gold dataset.",
    )
    pair_skill_options = ["All skills"]
    if not overall_pairs.empty:
        pair_skill_options.extend(
            sorted(
                {
                    value
                    for column in ("skill_a", "skill_b")
                    for value in overall_pairs[column].dropna().astype(str).tolist()
                }
            )
        )
    selected_pair_skill = st.selectbox("Skill focus", pair_skill_options, index=0)

    pair_frame = filter_skill_pairs(
        overall_pairs,
        min_threshold=pair_threshold,
        selected_skill=None if selected_pair_skill == "All skills" else selected_pair_skill,
    )
    company_focus = st.selectbox(
        "Company focus",
        ["All companies"] + sorted(company_pairs["company"].dropna().unique().tolist()) if not company_pairs.empty else ["All companies"],
        index=0,
    )

    if company_focus != "All companies":
        company_focus_pairs = company_pairs.loc[
            company_pairs["company"].astype(str).str.casefold().eq(str(company_focus).casefold())
        ].copy()
        company_focus_pairs = filter_skill_pairs(
            company_focus_pairs,
            min_threshold=pair_threshold,
            selected_skill=None if selected_pair_skill == "All skills" else selected_pair_skill,
        )
    else:
        company_focus_pairs = company_pairs.copy()
        company_focus_pairs = filter_skill_pairs(
            company_focus_pairs,
            min_threshold=pair_threshold,
            selected_skill=None if selected_pair_skill == "All skills" else selected_pair_skill,
        )

    if pair_frame.empty:
        st.info("No skill pairs match the current threshold and skill filter.")
    else:
        st.dataframe(
            pair_frame[["skill_a", "skill_b", "pair_count", "pct_b_given_a", "pct_a_given_b", "jaccard_similarity"]].head(20),
            use_container_width=True,
            hide_index=True,
        )

    if company_focus == "All companies":
        st.caption("Use the company selector to inspect company-specific skill combinations.")
    elif company_focus_pairs.empty:
        st.info(f"No skill pairs are available for {company_focus} with the current threshold and skill focus.")
    else:
        st.subheader(f"Company-specific combinations: {company_focus}")
        st.dataframe(
            company_focus_pairs[["skill_a", "skill_b", "pair_count", "pct_b_given_a", "pct_a_given_b", "jaccard_similarity"]].head(20),
            use_container_width=True,
            hide_index=True,
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
