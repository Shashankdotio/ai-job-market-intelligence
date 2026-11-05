"""Role-based skill intelligence from the Gold job-postings dataset."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Final

from ai_job_market.config import (
    GOLD_DATA_DIR,
    GOLD_JOB_POSTINGS_PATH,
    GOLD_ROLE_SKILL_COOCCURRENCE_PATH,
    GOLD_ROLE_SKILL_COUNTS_PATH,
    GOLD_ROLE_SKILL_SUMMARY_PATH,
)
from ai_job_market.skill_cooccurrence import _as_skill_list, build_skill_cooccurrence

MIN_ROLE_POSTINGS: Final[int] = 5
MIN_ROLE_PAIR_COUNT: Final[int] = 2
ROLE_ORDER: Final[tuple[str, ...]] = (
    "Data Scientist",
    "ML Engineer",
    "AI Engineer",
    "Data Engineer",
    "Data Analyst",
    "Software Engineer",
    "Other/Unclassified",
)
ROLE_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "Data Scientist": (
        "data scientist",
        "applied scientist",
        "research scientist",
        "ai scientist",
        "ml scientist",
        "scientist",
    ),
    "ML Engineer": (
        "machine learning engineer",
        "ml engineer",
        "ml systems engineer",
        "ml platform engineer",
        "machine learning",
        "ml researcher",
    ),
    "AI Engineer": (
        "ai engineer",
        "artificial intelligence engineer",
        "genai engineer",
        "generative ai engineer",
        "llm engineer",
        "large language model engineer",
    ),
    "Data Engineer": (
        "data engineer",
        "analytics engineer",
        "etl engineer",
        "data platform engineer",
        "big data engineer",
    ),
    "Data Analyst": (
        "data analyst",
        "analytics analyst",
        "bi analyst",
        "business intelligence analyst",
    ),
    "Software Engineer": (
        "software engineer",
        "backend engineer",
        "frontend engineer",
        "full stack engineer",
        "platform engineer",
        "infrastructure engineer",
        "systems engineer",
        "site reliability engineer",
    ),
}

SUMMARY_FIELDNAMES: Final[tuple[str, ...]] = (
    "role",
    "posting_count",
    "usable_skill_postings",
    "skill_coverage_pct",
    "distinctive_skill_count",
    "top_skill",
    "top_skill_count",
)
COUNT_FIELDNAMES: Final[tuple[str, ...]] = (
    "role",
    "skill",
    "skill_count",
    "skill_pct_of_role",
    "overall_skill_pct",
    "relative_demand_pct",
    "is_distinctive",
)
COOCCURRENCE_FIELDNAMES: Final[tuple[str, ...]] = (
    "role",
    "skill_a",
    "skill_b",
    "pair_count",
    "skill_a_count",
    "skill_b_count",
    "pct_b_given_a",
    "pct_a_given_b",
    "jaccard_similarity",
)


def _load_job_postings(path: str | Path = GOLD_JOB_POSTINGS_PATH) -> list[dict[str, Any]]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def classify_role(title: Any) -> str:
    """Use deterministic title keyword rules to map a job title to a role."""
    value = str(title or "").strip()
    if not value:
        return "Other/Unclassified"
    normalized = value.casefold()
    for role, keywords in ROLE_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return role
    return "Other/Unclassified"


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    output = dict(record)
    output["role"] = classify_role(record.get("title"))
    output["skill_list"] = _as_skill_list(record.get("skills"))
    return output


def build_role_skill_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize posting counts and skill coverage by role."""
    normalized = [_normalize_record(record) for record in records]
    role_postings: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        role_postings[record["role"]].append(record)

    overall_skill_postings = sum(1 for record in normalized if record["skill_list"])
    overall_skill_frequency: Counter[str] = Counter()
    for record in normalized:
        overall_skill_frequency.update(record["skill_list"])

    summary_rows: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        postings = role_postings.get(role, [])
        posting_count = len(postings)
        usable_skill_postings = sum(1 for record in postings if record["skill_list"])
        skill_coverage_pct = (usable_skill_postings / posting_count * 100.0) if posting_count else 0.0
        role_skill_frequency: Counter[str] = Counter()
        for record in postings:
            role_skill_frequency.update(record["skill_list"])
        top_skill = ""
        top_skill_count = 0
        if role_skill_frequency:
            top_skill, top_skill_count = max(role_skill_frequency.items(), key=lambda item: (item[1], item[0].casefold()))
        distinctive_skill_count = 0
        if posting_count and overall_skill_postings:
            distinctive_skill_count = sum(
                1
                for skill, skill_count in role_skill_frequency.items()
                if (skill_count / posting_count) > (overall_skill_frequency.get(skill, 0) / overall_skill_postings)
            )
        summary_rows.append(
            {
                "role": role,
                "posting_count": posting_count,
                "usable_skill_postings": usable_skill_postings,
                "skill_coverage_pct": round(skill_coverage_pct, 2),
                "distinctive_skill_count": distinctive_skill_count,
                "top_skill": top_skill,
                "top_skill_count": top_skill_count,
            }
        )

    return summary_rows


def build_role_skill_counts(records: list[dict[str, Any]], *, min_role_postings: int = MIN_ROLE_POSTINGS) -> list[dict[str, Any]]:
    """Count each skill once per posting within each role, comparing against overall demand."""
    normalized = [_normalize_record(record) for record in records]
    overall_skill_postings = sum(1 for record in normalized if record["skill_list"])
    overall_skill_frequency: Counter[str] = Counter()
    for record in normalized:
        overall_skill_frequency.update(record["skill_list"])

    role_postings: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        role_postings[record["role"]].append(record)

    rows: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        postings = role_postings.get(role, [])
        if len(postings) < min_role_postings:
            continue
        role_skill_frequency: Counter[str] = Counter()
        for record in postings:
            role_skill_frequency.update(record["skill_list"])
        for skill, skill_count in sorted(role_skill_frequency.items(), key=lambda item: (-item[1], item[0].casefold())):
            role_pct = (skill_count / len(postings)) * 100.0
            overall_pct = (overall_skill_frequency.get(skill, 0) / overall_skill_postings * 100.0) if overall_skill_postings else 0.0
            relative_demand_pct = role_pct - overall_pct
            rows.append(
                {
                    "role": role,
                    "skill": skill,
                    "skill_count": skill_count,
                    "skill_pct_of_role": round(role_pct, 2),
                    "overall_skill_pct": round(overall_pct, 4),
                    "relative_demand_pct": round(relative_demand_pct, 4),
                    "is_distinctive": bool(relative_demand_pct > 0),
                }
            )
    return rows


def build_role_skill_cooccurrence(records: list[dict[str, Any]], *, min_role_postings: int = MIN_ROLE_POSTINGS) -> list[dict[str, Any]]:
    """Compute pairwise skill co-occurrence within each role using the same semantics as the overall co-occurrence module."""
    normalized = [_normalize_record(record) for record in records]
    role_postings: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        role_postings[record["role"]].append(record)

    rows: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        postings = role_postings.get(role, [])
        if len(postings) < min_role_postings:
            continue
        role_records = [{**record, "role": role} for record in postings]
        pairs = build_skill_cooccurrence(role_records, group_by="role", min_cooccurrence=MIN_ROLE_PAIR_COUNT)
        for pair in pairs:
            row = {
                "role": pair["role"],
                "skill_a": pair["skill_a"],
                "skill_b": pair["skill_b"],
                "pair_count": pair["pair_count"],
                "skill_a_count": pair["skill_a_count"],
                "skill_b_count": pair["skill_b_count"],
                "pct_b_given_a": pair["pct_b_given_a"],
                "pct_a_given_b": pair["pct_a_given_b"],
                "jaccard_similarity": pair["jaccard_similarity"],
            }
            rows.append(row)
    return rows


def _write_csv(path: str | Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return output_path


def write_role_skill_outputs(
    records: list[dict[str, Any]] | None = None,
    *,
    job_postings_path: str | Path = GOLD_JOB_POSTINGS_PATH,
    output_dir: str | Path = GOLD_DATA_DIR,
    min_role_postings: int = MIN_ROLE_POSTINGS,
) -> dict[str, Path]:
    """Generate role-based skill summary, counts, and pair outputs in the Gold directory."""
    if records is None:
        records = _load_job_postings(job_postings_path)

    if not records:
        summary_rows: list[dict[str, Any]] = []
        count_rows: list[dict[str, Any]] = []
        cooccurrence_rows: list[dict[str, Any]] = []
    else:
        summary_rows = build_role_skill_summary(records)
        count_rows = build_role_skill_counts(records, min_role_postings=min_role_postings)
        cooccurrence_rows = build_role_skill_cooccurrence(records, min_role_postings=min_role_postings)

    output_directory = Path(output_dir)
    output_paths = {
        "summary": _write_csv(
            GOLD_ROLE_SKILL_SUMMARY_PATH if output_dir == GOLD_DATA_DIR else output_directory / "role_skill_summary.csv",
            SUMMARY_FIELDNAMES,
            summary_rows,
        ),
        "counts": _write_csv(
            GOLD_ROLE_SKILL_COUNTS_PATH if output_dir == GOLD_DATA_DIR else output_directory / "role_skill_counts.csv",
            COUNT_FIELDNAMES,
            count_rows,
        ),
        "cooccurrence": _write_csv(
            GOLD_ROLE_SKILL_COOCCURRENCE_PATH if output_dir == GOLD_DATA_DIR else output_directory / "role_skill_cooccurrence.csv",
            COOCCURRENCE_FIELDNAMES,
            cooccurrence_rows,
        ),
    }
    return output_paths


def main() -> int:
    """Generate the Gold role-based skill analytics outputs."""
    write_role_skill_outputs(
        job_postings_path=GOLD_JOB_POSTINGS_PATH,
        output_dir=GOLD_DATA_DIR,
        min_role_postings=MIN_ROLE_POSTINGS,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
