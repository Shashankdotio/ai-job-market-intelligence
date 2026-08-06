"""Gold-backed, in-memory analytics used by the dashboard presentation layer."""

import json
import re
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True, slots=True)
class DashboardFilters:
    """Global filter state applied consistently across all dashboard pages."""

    companies: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()
    search_query: str = ""


def enrich_jobs(jobs: pd.DataFrame) -> pd.DataFrame:
    """Add presentation-only fields derived from published gold job records."""
    enriched = jobs.copy()
    enriched["skill_list"] = enriched["skills"].map(_parse_skills)
    enriched["work_mode"] = enriched["location"].map(classify_work_mode)
    enriched["seniority"] = enriched["title"].map(classify_seniority)
    return enriched


def apply_filters(jobs: pd.DataFrame, filters: DashboardFilters) -> pd.DataFrame:
    """Apply global filter state to the gold-backed job dataset."""
    filtered = jobs.copy()
    if filters.companies:
        filtered = filtered.loc[filtered["company"].isin(filters.companies)]
    if filters.locations:
        filtered = filtered.loc[filtered["location"].isin(filters.locations)]
    if filters.skills:
        selected_skills = set(filters.skills)
        filtered = filtered.loc[
            filtered["skill_list"].map(
                lambda skills: bool(selected_skills & set(skills))
            )
        ]
    if filters.work_modes:
        filtered = filtered.loc[filtered["work_mode"].isin(filters.work_modes)]
    if filters.search_query.strip():
        search_pattern = re.escape(filters.search_query.strip())
        searchable_columns = ("title", "company", "location", "department")
        text_matches = pd.Series(False, index=filtered.index)
        for column in searchable_columns:
            text_matches |= filtered[column].str.contains(
                search_pattern,
                case=False,
                na=False,
                regex=True,
            )
        skill_matches = filtered["skill_list"].map(
            lambda skills: any(
                filters.search_query.lower() in skill.lower() for skill in skills
            )
        )
        filtered = filtered.loc[text_matches | skill_matches]
    return filtered


def count_by_column(
    jobs: pd.DataFrame,
    column: str,
    *,
    label: str | None = None,
) -> pd.DataFrame:
    """Count a job field for chart-ready ranking tables."""
    result_label = label or column
    values = jobs[column].replace("", pd.NA).dropna()
    return (
        values.value_counts()
        .rename_axis(result_label)
        .reset_index(name="job_count")
    )


def skill_frequency(jobs: pd.DataFrame) -> pd.DataFrame:
    """Count skills across the currently filtered job records."""
    skills = jobs["skill_list"].explode().dropna()
    if skills.empty:
        return pd.DataFrame(columns=["skill", "job_count"])
    return skills.value_counts().rename_axis("skill").reset_index(name="job_count")


def company_skill_frequency(jobs: pd.DataFrame) -> pd.DataFrame:
    """Count skills per company for a filtered job view."""
    exploded = jobs[["company", "skill_list"]].explode("skill_list").dropna()
    if exploded.empty:
        return pd.DataFrame(columns=["company", "skill", "job_count"])
    return (
        exploded.groupby(["company", "skill_list"])
        .size()
        .reset_index(name="job_count")
        .rename(columns={"skill_list": "skill"})
        .sort_values(["job_count", "company", "skill"], ascending=[False, True, True])
    )


def jobs_with_skill(jobs: pd.DataFrame, skill: str) -> pd.DataFrame:
    """Return filtered jobs that request a selected skill."""
    return jobs.loc[jobs["skill_list"].map(lambda skills: skill in skills)].copy()


def classify_work_mode(location: object) -> str:
    """Classify published location text into an explainable work arrangement."""
    value = str(location or "").lower()
    if "remote" in value:
        return "Remote"
    if "hybrid" in value:
        return "Hybrid"
    return "Onsite"


def classify_seniority(title: object) -> str:
    """Classify title text into a presentation-level seniority bucket."""
    value = str(title or "").lower()
    if any(term in value for term in ("chief", "vice president", "vp", "head of")):
        return "Leadership"
    if "director" in value:
        return "Director"
    if any(term in value for term in ("principal", "staff", "senior", " sr.")):
        return "Senior"
    if "manager" in value:
        return "Manager"
    if any(
        term in value
        for term in ("intern", "junior", "associate", "entry", "new grad")
    ):
        return "Entry"
    return "Mid-level"


def unique_values(jobs: pd.DataFrame, column: str) -> list[str]:
    """Return sorted non-empty values for filter controls."""
    return sorted(value for value in jobs[column].dropna().unique() if value)


def _parse_skills(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(skill) for skill in value)
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(skill) for skill in parsed if isinstance(skill, str))
