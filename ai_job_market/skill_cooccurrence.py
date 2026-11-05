"""Skill co-occurrence analytics derived from the gold job-postings dataset."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from itertools import combinations
from pathlib import Path
from typing import Any, Final

from ai_job_market.config import (
    GOLD_DATA_DIR,
    GOLD_JOB_POSTINGS_PATH,
    GOLD_SKILL_COOCCURRENCE_BY_COMPANY_PATH,
    GOLD_SKILL_COOCCURRENCE_BY_TITLE_PATH,
    GOLD_SKILL_COOCCURRENCE_PATH,
)

DEFAULT_MIN_COOCCURRENCE: Final[int] = 2
OVERALL_FIELDNAMES: Final[tuple[str, ...]] = (
    "skill_a",
    "skill_b",
    "pair_count",
    "skill_a_count",
    "skill_b_count",
    "pct_b_given_a",
    "pct_a_given_b",
    "jaccard_similarity",
)
GROUPED_FIELDNAMES: Final[tuple[str, ...]] = (
    "company",
    "skill_a",
    "skill_b",
    "pair_count",
    "skill_a_count",
    "skill_b_count",
    "pct_b_given_a",
    "pct_a_given_b",
    "jaccard_similarity",
)
TITLE_FIELDNAMES: Final[tuple[str, ...]] = (
    "title",
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
    """Read a gold job-postings CSV into a list of row dictionaries."""
    input_path = Path(path)
    if not input_path.exists():
        return []
    with input_path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _canonical_skill_label(raw: Any) -> str:
    """Normalize skill casing into a stable display label while tracking case-insensitively."""
    cleaned = str(raw or "").strip()
    if not cleaned:
        return ""

    compact = re.sub(r"[^A-Za-z0-9+.#]+", " ", cleaned).strip()
    if not compact:
        return ""

    tokens = [token for token in compact.split() if token]
    if not tokens:
        return ""

    canonical_tokens: list[str] = []
    for token in tokens:
        letters = "".join(ch for ch in token if ch.isalpha())
        if not letters:
            canonical_tokens.append(token)
            continue
        if len(letters) <= 3:
            canonical_tokens.append(letters.upper())
        else:
            canonical_tokens.append(f"{letters[0].upper()}{letters[1:].lower()}")
    return " ".join(canonical_tokens)


def _as_skill_list(raw: Any) -> list[str]:
    """Normalize a job's skills field to a deduplicated, non-empty list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, tuple):
        values = list(raw)
    elif isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            values = [raw]
        else:
            if isinstance(parsed, list):
                values = parsed
            elif isinstance(parsed, str):
                values = [parsed]
            else:
                values = []
    else:
        values = [raw]

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        canonical = _canonical_skill_label(value)
        if not canonical:
            continue
        key = canonical.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(canonical)
    return normalized


def _sorted_skill_pair(skill_a: str, skill_b: str) -> tuple[str, str]:
    return (skill_a, skill_b) if skill_a.casefold() <= skill_b.casefold() else (skill_b, skill_a)


def build_skill_frequency(
    records: Sequence[dict[str, Any]],
    *,
    group_by: str | None = None,
) -> list[dict[str, Any]]:
    """Count each skill once per posting for either the full dataset or a group."""
    counts: defaultdict[str | Any, Counter[str]] = defaultdict(Counter)
    for record in records:
        group_key: str | Any = "__all__" if group_by is None else str(record.get(group_by, "")).strip()
        if group_by and not group_key:
            continue
        for skill in _as_skill_list(record.get("skills")):
            counts[group_key][skill] += 1

    rows: list[dict[str, Any]] = []
    for group_key, group_counts in counts.items():
        for skill, count in sorted(group_counts.items(), key=lambda item: (-item[1], item[0].casefold())):
            row: dict[str, Any] = {"skill": skill, "job_count": count}
            if group_by is not None:
                row[group_by] = group_key
            rows.append(row)
    return rows


def build_skill_cooccurrence(
    records: Sequence[dict[str, Any]],
    *,
    group_by: str | None = None,
    min_cooccurrence: int = DEFAULT_MIN_COOCCURRENCE,
) -> list[dict[str, Any]]:
    """Compute pairwise skill co-occurrence with conditional percentages and Jaccard similarity."""
    if min_cooccurrence < 1:
        min_cooccurrence = 1

    skill_counts: defaultdict[str | Any, Counter[str]] = defaultdict(Counter)
    pair_counts: defaultdict[str | Any, Counter[tuple[str, str]]] = defaultdict(Counter)

    for record in records:
        group_key: str | Any = "__all__" if group_by is None else str(record.get(group_by, "")).strip()
        if group_by and not group_key:
            continue
        skills = _as_skill_list(record.get("skills"))
        if len(skills) < 2:
            continue
        unique_skills = sorted(set(skills), key=lambda skill: skill.casefold())
        for skill in unique_skills:
            skill_counts[group_key][skill] += 1
        for skill_a, skill_b in combinations(unique_skills, 2):
            pair = _sorted_skill_pair(skill_a, skill_b)
            pair_counts[group_key][pair] += 1

    rows: list[dict[str, Any]] = []
    for group_key, cooccurrence in pair_counts.items():
        for (skill_a, skill_b), pair_count in cooccurrence.items():
            if pair_count < min_cooccurrence:
                continue
            skill_a_count = skill_counts[group_key][skill_a]
            skill_b_count = skill_counts[group_key][skill_b]
            if skill_a_count == 0:
                pct_b_given_a = 0.0
            else:
                pct_b_given_a = (pair_count / skill_a_count) * 100.0
            if skill_b_count == 0:
                pct_a_given_b = 0.0
            else:
                pct_a_given_b = (pair_count / skill_b_count) * 100.0
            denominator = skill_a_count + skill_b_count - pair_count
            jaccard_similarity = (pair_count / denominator) if denominator else 0.0
            row: dict[str, Any] = {
                "skill_a": skill_a,
                "skill_b": skill_b,
                "pair_count": pair_count,
                "skill_a_count": skill_a_count,
                "skill_b_count": skill_b_count,
                "pct_b_given_a": round(pct_b_given_a, 4),
                "pct_a_given_b": round(pct_a_given_b, 4),
                "jaccard_similarity": round(jaccard_similarity, 4),
            }
            if group_by is not None:
                row[group_by] = group_key
            rows.append(row)

    rows.sort(
        key=lambda row: (
            str(row.get(group_by, "")).casefold() if group_by else "",
            -int(row["pair_count"]),
            str(row["skill_a"]).casefold(),
            str(row["skill_b"]).casefold(),
        )
    )
    return rows


def _write_csv(path: str | Path, fieldnames: Sequence[str], rows: Iterable[dict[str, Any]]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return output_path


def write_skill_cooccurrence_outputs(
    records: Sequence[dict[str, Any]] | None = None,
    *,
    job_postings_path: str | Path = GOLD_JOB_POSTINGS_PATH,
    output_dir: str | Path = GOLD_DATA_DIR,
    min_cooccurrence: int = DEFAULT_MIN_COOCCURRENCE,
) -> dict[str, Path]:
    """Generate overall and grouped skill co-occurrence CSVs in the Gold directory."""
    if records is None:
        records = _load_job_postings(job_postings_path)

    overall_rows = build_skill_cooccurrence(records, min_cooccurrence=min_cooccurrence)
    company_rows = build_skill_cooccurrence(
        records,
        group_by="company",
        min_cooccurrence=min_cooccurrence,
    )
    title_rows = build_skill_cooccurrence(
        records,
        group_by="title",
        min_cooccurrence=min_cooccurrence,
    )

    output_directory = Path(output_dir)
    use_empty_schema = not records or (not overall_rows and not company_rows and not title_rows)
    output_paths = {
        "overall": _write_csv(
            GOLD_SKILL_COOCCURRENCE_PATH if output_dir == GOLD_DATA_DIR else output_directory / "skill_cooccurrence.csv",
            OVERALL_FIELDNAMES if use_empty_schema else OVERALL_FIELDNAMES,
            overall_rows,
        ),
        "by_company": _write_csv(
            GOLD_SKILL_COOCCURRENCE_BY_COMPANY_PATH if output_dir == GOLD_DATA_DIR else output_directory / "skill_cooccurrence_by_company.csv",
            OVERALL_FIELDNAMES if use_empty_schema else GROUPED_FIELDNAMES,
            company_rows,
        ),
        "by_title": _write_csv(
            GOLD_SKILL_COOCCURRENCE_BY_TITLE_PATH if output_dir == GOLD_DATA_DIR else output_directory / "skill_cooccurrence_by_title.csv",
            OVERALL_FIELDNAMES if use_empty_schema else TITLE_FIELDNAMES,
            title_rows,
        ),
    }
    return output_paths


def main() -> int:
    """Generate co-occurrence Gold datasets from the current Gold job-postings CSV."""
    write_skill_cooccurrence_outputs(
        job_postings_path=GOLD_JOB_POSTINGS_PATH,
        output_dir=GOLD_DATA_DIR,
        min_cooccurrence=DEFAULT_MIN_COOCCURRENCE,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
