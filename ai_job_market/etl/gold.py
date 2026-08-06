"""Build dashboard-ready gold aggregates from silver job-posting records."""

import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from typing import Final


COMPANY_COUNT_COLUMNS: Final[tuple[str, ...]] = ("company", "job_count")
SKILL_COUNT_COLUMNS: Final[tuple[str, ...]] = ("skill", "job_count")
COMPANY_SKILL_COUNT_COLUMNS: Final[tuple[str, ...]] = (
    "company",
    "skill",
    "job_count",
)
JOB_POSTING_COLUMNS: Final[tuple[str, ...]] = (
    "snapshot_id",
    "job_key",
    "provider",
    "external_job_id",
    "company",
    "title",
    "location",
    "updated_at",
    "job_url",
    "department",
    "office",
    "collected_at",
    "skills",
)


def build_company_counts(
    records: Sequence[dict[str, str]],
) -> list[dict[str, int | str]]:
    """Count active records by company in deterministic display order."""
    counts = Counter(record["company"] for record in records)
    return [
        {"company": company, "job_count": count}
        for company, count in _sorted_counts(counts)
    ]


def build_skill_counts(records: Sequence[dict[str, str]]) -> list[dict[str, int | str]]:
    """Count extracted skills across normalized job postings."""
    counts: Counter[str] = Counter()
    for record in records:
        counts.update(json.loads(record["skills"]))
    return [
        {"skill": skill, "job_count": count}
        for skill, count in _sorted_counts(counts)
    ]


def build_company_skill_counts(
    records: Sequence[dict[str, str]],
) -> list[dict[str, int | str]]:
    """Count extracted skills by company for employer comparison views."""
    counts: Counter[tuple[str, str]] = Counter()
    for record in records:
        company = record["company"]
        counts.update((company, skill) for skill in json.loads(record["skills"]))

    return [
        {"company": company, "skill": skill, "job_count": count}
        for (company, skill), count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
        )
    ]


def build_job_postings(
    records: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    """Publish dashboard-safe job detail fields from the silver dataset."""
    return [
        {column: record[column] for column in JOB_POSTING_COLUMNS}
        for record in sorted(
            records,
            key=lambda record: record["updated_at"],
            reverse=True,
        )
    ]


def build_market_metadata(
    records: Sequence[dict[str, str]],
    *,
    snapshot_id: str,
    generated_at: str,
) -> dict[str, int | str | None]:
    """Build freshness and high-level metrics for dashboard display."""
    all_skills = {
        skill
        for record in records
        for skill in json.loads(record["skills"])
    }
    locations = {record["location"] for record in records if record["location"]}
    return {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "source_latest_updated_at": _latest_source_update(records),
        "total_jobs": len(records),
        "total_companies": len({record["company"] for record in records}),
        "total_locations": len(locations),
        "total_skills": len(all_skills),
    }


def _sorted_counts(counts: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _latest_source_update(records: Sequence[dict[str, str]]) -> str | None:
    parsed_updates: list[tuple[datetime, str]] = []
    for record in records:
        value = record["updated_at"]
        if not value:
            continue
        try:
            parsed_updates.append((datetime.fromisoformat(value), value))
        except ValueError:
            continue
    return max(parsed_updates, default=(None, None), key=lambda item: item[0])[1]
