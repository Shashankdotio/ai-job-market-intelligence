"""Cached Streamlit access to the dashboard's read-only gold repository."""

from pathlib import Path

import pandas as pd
import streamlit as st

from ai_job_market.config import (
    GOLD_COMPANY_ACTIVITY_PATH,
    GOLD_HIRING_TRENDS_DAILY_PATH,
    GOLD_HIRING_TRENDS_WEEKLY_PATH,
    GOLD_JOB_CHANGES_PATH,
    GOLD_LIFECYCLE_SUMMARY_PATH,
    GOLD_SKILL_COOCCURRENCE_BY_COMPANY_PATH,
    GOLD_SKILL_COOCCURRENCE_PATH,
    GOLD_SKILL_DEMAND_TRENDS_PATH,
)
from dashboard.data_repository import GoldData, load_gold_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_DIRECTORY = PROJECT_ROOT / "data" / "gold"

HISTORICAL_DATA_PATHS = {
    "hiring_trends_daily": GOLD_HIRING_TRENDS_DAILY_PATH,
    "hiring_trends_weekly": GOLD_HIRING_TRENDS_WEEKLY_PATH,
    "company_activity": GOLD_COMPANY_ACTIVITY_PATH,
    "lifecycle_summary": GOLD_LIFECYCLE_SUMMARY_PATH,
    "job_changes": GOLD_JOB_CHANGES_PATH,
    "skill_demand_trends": GOLD_SKILL_DEMAND_TRENDS_PATH,
}

HISTORICAL_COLUMNS = {
    "hiring_trends_daily": ["date", "job_count"],
    "hiring_trends_weekly": ["week_start", "job_count"],
    "company_activity": [
        "company",
        "new_jobs",
        "closed_jobs",
        "reopened_jobs",
        "current_active_jobs",
        "current_suspected_closed_jobs",
    ],
    "lifecycle_summary": ["metric", "value", "as_of"],
    "job_changes": ["event_date", "update_count", "unique_jobs_updated"],
    "skill_demand_trends": ["date", "skill", "job_count"],
}

SKILL_COOCCURRENCE_PATHS = {
    "overall": GOLD_SKILL_COOCCURRENCE_PATH,
    "by_company": GOLD_SKILL_COOCCURRENCE_BY_COMPANY_PATH,
}

SKILL_COOCCURRENCE_COLUMNS = {
    "overall": [
        "skill_a",
        "skill_b",
        "pair_count",
        "skill_a_count",
        "skill_b_count",
        "pct_b_given_a",
        "pct_a_given_b",
        "jaccard_similarity",
    ],
    "by_company": [
        "company",
        "skill_a",
        "skill_b",
        "pair_count",
        "skill_a_count",
        "skill_b_count",
        "pct_b_given_a",
        "pct_a_given_b",
        "jaccard_similarity",
    ],
}


@st.cache_data(ttl=300, show_spinner="Loading market intelligence data...")
def load_dashboard_data(gold_directory: str) -> GoldData:
    """Load gold artifacts with a short cache suitable for scheduled refreshes."""
    return load_gold_data(Path(gold_directory))


@st.cache_data(ttl=300, show_spinner="Loading historical analytics...")
def load_historical_analytics_data() -> dict[str, pd.DataFrame]:
    """Load and normalize Gold historical analytics datasets into chart-ready DataFrames."""
    frames: dict[str, pd.DataFrame] = {}
    for name, path in HISTORICAL_DATA_PATHS.items():
        columns = HISTORICAL_COLUMNS[name]
        if not path.exists():
            frames[name] = pd.DataFrame(columns=columns)
            continue
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            frame = pd.DataFrame(columns=columns)
        if list(frame.columns) != columns:
            missing = [column for column in columns if column not in frame.columns]
            for column in missing:
                frame[column] = pd.Series([None] * len(frame), index=frame.index)
            frame = frame.reindex(columns=columns)
        frames[name] = frame
    return frames


@st.cache_data(ttl=300, show_spinner="Loading skill co-occurrence data...")
def load_skill_cooccurrence_data(gold_directory: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """Load the Phase 4A skill co-occurrence Gold outputs with safe empty fallbacks."""
    base_directory = Path(gold_directory) if gold_directory is not None else GOLD_DIRECTORY
    frames: dict[str, pd.DataFrame] = {}
    for name, path in (
        ("overall", base_directory / "skill_cooccurrence.csv"),
        ("by_company", base_directory / "skill_cooccurrence_by_company.csv"),
    ):
        columns = SKILL_COOCCURRENCE_COLUMNS[name]
        if not path.exists():
            frames[name] = pd.DataFrame(columns=columns)
            continue
        try:
            frame = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            frame = pd.DataFrame(columns=columns)
        if list(frame.columns) != columns:
            missing = [column for column in columns if column not in frame.columns]
            for column in missing:
                frame[column] = pd.Series([None] * len(frame), index=frame.index)
            frame = frame.reindex(columns=columns)
        frames[name] = frame
    return frames
