"""Market-level hiring intelligence from historical and lifecycle data."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

from ai_job_market.config import (
    GOLD_COMPANY_MOVEMENT_PATH,
    GOLD_DATA_DIR,
    GOLD_JOB_POSTINGS_PATH,
    GOLD_MARKET_INTELLIGENCE_DAILY_PATH,
    GOLD_MARKET_INTELLIGENCE_WEEKLY_PATH,
    GOLD_ROLE_HIRING_TRENDS_PATH,
    GOLD_SKILL_MOMENTUM_PATH,
    INGESTION_JOB_EVENTS_DIR,
)
from ai_job_market.role_skill_intelligence import classify_role

DAILY_FIELDNAMES: Final[tuple[str, ...]] = (
    "date",
    "active_jobs",
    "previous_period_active_jobs",
    "delta_active_jobs",
    "delta_pct",
    "sample_size",
)
WEEKLY_FIELDNAMES: Final[tuple[str, ...]] = (
    "week_start",
    "active_jobs",
    "previous_period_active_jobs",
    "delta_active_jobs",
    "delta_pct",
    "sample_size",
)
COMPANY_MOVEMENT_FIELDNAMES: Final[tuple[str, ...]] = (
    "company",
    "current_active_jobs",
    "previous_period_active_jobs",
    "delta_active_jobs",
    "delta_pct",
    "status",
    "sample_size",
)
ROLE_TREND_FIELDNAMES: Final[tuple[str, ...]] = (
    "date",
    "role",
    "role_count",
    "previous_period_role_count",
    "delta_count",
    "delta_pct",
    "sample_size",
)
SKILL_MOMENTUM_FIELDNAMES: Final[tuple[str, ...]] = (
    "skill",
    "current_period_jobs",
    "previous_period_jobs",
    "delta_jobs",
    "delta_pct",
    "sample_size",
    "coverage_pct",
    "status",
)
MIN_TRACKING_SAMPLE: Final[int] = 2


def _as_utc(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        candidate = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_iso_date(value: Any) -> str | None:
    dt = _as_utc(value)
    if dt is None:
        return None
    return dt.date().isoformat()


def _as_iso_week(value: Any) -> str | None:
    dt = _as_utc(value)
    if dt is None:
        return None
    week_start = dt - timedelta(days=dt.weekday())
    return week_start.date().isoformat()


def _iter_jsonl_records(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    records: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
    return records


def _iter_event_records(events_dir: str | Path | None = None) -> list[dict[str, Any]]:
    target = Path(events_dir) if events_dir is not None else INGESTION_JOB_EVENTS_DIR
    if not target.exists():
        return []
    raw_records: list[dict[str, Any]] = []
    for file_path in sorted(target.glob("*.jsonl"), key=lambda item: item.name):
        raw_records.extend(_iter_jsonl_records(file_path))

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for record in raw_records:
        key = (
            str(record.get("event_id") or ""),
            str(record.get("event_type") or ""),
            str(record.get("company_slug") or ""),
            str(record.get("external_job_id") or ""),
            str(record.get("occurred_at") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return sorted(deduped, key=lambda record: str(record.get("occurred_at") or ""))


def _job_identity(record: dict[str, Any]) -> str:
    key = str(record.get("job_key") or "").strip()
    if key:
        return key
    company = str(record.get("company_slug") or "").strip()
    external = str(record.get("external_job_id") or "").strip()
    if company and external:
        return f"{company}:{external}"
    return ""


def _safe_pct(delta: float, baseline: float) -> float:
    if baseline == 0:
        if delta == 0:
            return 0.0
        return 100.0 if delta > 0 else -100.0
    return (delta / baseline) * 100.0


def _is_synthetic_history_record(record: dict[str, Any]) -> bool:
    provider = str(record.get("provider") or "").casefold()
    company = str(record.get("company_slug") or "").casefold()
    job_key = str(record.get("job_key") or "").casefold()
    suspicious = {"fake", "interrupt", "good-company", "first-company"}
    return provider in suspicious or company in suspicious or "fake:" in job_key or "interrupt:" in job_key


def _has_synthetic_history(events_dir: str | Path | None = None) -> bool:
    records = _iter_event_records(events_dir)
    if not records:
        return False
    return all(_is_synthetic_history_record(record) for record in records)


def _format_status(value: float) -> str:
    if value > 0:
        return "increasing"
    if value < 0:
        return "decreasing"
    return "stable"


def build_daily_active_job_changes(
    events_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Track active jobs over time using discovered, closed, and reopened job events."""
    if _has_synthetic_history(events_dir):
        return []
    active_by_job: dict[str, str] = {}
    jobs_by_date: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in _iter_event_records(events_dir):
        date = _as_iso_date(record.get("occurred_at"))
        if not date:
            continue
        jobs_by_date[date].append(record)

    ordered_dates = sorted(jobs_by_date)
    rows: list[dict[str, Any]] = []
    previous_active = 0
    for date in ordered_dates:
        for record in jobs_by_date[date]:
            event_type = str(record.get("event_type") or "")
            job_key = _job_identity(record)
            if not job_key:
                continue
            if event_type == "discovered":
                active_by_job[job_key] = "active"
            elif event_type == "closed":
                active_by_job[job_key] = "closed"
            elif event_type == "reopened":
                active_by_job[job_key] = "active"
        active_jobs = sum(1 for state in active_by_job.values() if state == "active")
        delta = active_jobs - previous_active
        rows.append(
            {
                "date": date,
                "active_jobs": active_jobs,
                "previous_period_active_jobs": previous_active,
                "delta_active_jobs": delta,
                "delta_pct": round(_safe_pct(delta, previous_active), 4),
                "sample_size": active_jobs,
            }
        )
        previous_active = active_jobs
    return rows


def build_weekly_active_job_changes(
    events_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Aggregate the daily active-job changes into weekly periods."""
    if _has_synthetic_history(events_dir):
        return []
    daily_rows = build_daily_active_job_changes(events_dir)
    if not daily_rows:
        return []
    weekly: defaultdict[str, dict[str, Any]] = defaultdict(dict)
    for row in daily_rows:
        week_start = _as_iso_week(row["date"])
        if week_start is None:
            continue
        weekly[week_start] = {
            "week_start": week_start,
            "active_jobs": row["active_jobs"],
            "sample_size": row["sample_size"],
        }

    ordered_weeks = sorted(weekly)
    rows: list[dict[str, Any]] = []
    previous_active = 0
    for week_start in ordered_weeks:
        active_jobs = int(weekly[week_start]["active_jobs"])
        delta = active_jobs - previous_active
        rows.append(
            {
                "week_start": week_start,
                "active_jobs": active_jobs,
                "previous_period_active_jobs": previous_active,
                "delta_active_jobs": delta,
                "delta_pct": round(_safe_pct(delta, previous_active), 4),
                "sample_size": weekly[week_start]["sample_size"],
            }
        )
        previous_active = active_jobs
    return rows


def build_company_movement(
    events_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Compare current company job counts with the previous period to show activity movement."""
    if _has_synthetic_history(events_dir):
        return []
    company_state: defaultdict[str, dict[str, str]] = defaultdict(dict)
    counts_by_company_date: defaultdict[str, defaultdict[str, int]] = defaultdict(lambda: defaultdict(int))

    for record in _iter_event_records(events_dir):
        company = str(record.get("company_slug") or "").strip()
        if not company:
            continue
        date = _as_iso_date(record.get("occurred_at"))
        if not date:
            continue
        job_key = _job_identity(record)
        if not job_key:
            continue
        event_type = str(record.get("event_type") or "")
        if event_type == "discovered":
            company_state[company][job_key] = "active"
        elif event_type == "closed":
            company_state[company][job_key] = "closed"
        elif event_type == "reopened":
            company_state[company][job_key] = "active"
        counts_by_company_date[company][date] = sum(
            1 for state in company_state[company].values() if state == "active"
        )

    if not counts_by_company_date:
        return []

    rows: list[dict[str, Any]] = []
    for company, values in counts_by_company_date.items():
        dates = sorted(values)
        if not dates:
            continue
        current_active = values[dates[-1]]
        previous_active = values[dates[-2]] if len(dates) > 1 else 0
        delta = current_active - previous_active
        rows.append(
            {
                "company": company,
                "current_active_jobs": current_active,
                "previous_period_active_jobs": previous_active,
                "delta_active_jobs": delta,
                "delta_pct": round(_safe_pct(delta, previous_active), 4),
                "status": _format_status(delta),
                "sample_size": current_active,
            }
        )
    rows.sort(key=lambda row: (-abs(int(row["delta_active_jobs"])), str(row["company"]).casefold()))
    return rows


def build_role_hiring_trends(
    events_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Model role-specific hiring activity over time from discovered jobs."""
    if _has_synthetic_history(events_dir):
        return []
    date_role_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for record in _iter_event_records(events_dir):
        if str(record.get("event_type") or "") != "discovered":
            continue
        date = _as_iso_date(record.get("occurred_at"))
        if not date:
            continue
        role = classify_role(record.get("title"))
        date_role_counts[date][role] += 1

    if not date_role_counts:
        return []

    rows: list[dict[str, Any]] = []
    ordered_dates = sorted(date_role_counts)
    previous_by_role: Counter[str] = Counter()
    for date in ordered_dates:
        current_by_role = date_role_counts[date]
        for role, count in sorted(current_by_role.items()):
            previous_count = previous_by_role.get(role, 0)
            delta = count - previous_count
            rows.append(
                {
                    "date": date,
                    "role": role,
                    "role_count": count,
                    "previous_period_role_count": previous_count,
                    "delta_count": delta,
                    "delta_pct": round(_safe_pct(delta, previous_count), 4),
                    "sample_size": count,
                }
            )
        previous_by_role = current_by_role
    return rows


def build_skill_momentum(
    skill_history_path: str | Path | None = None,
    *,
    min_sample_size: int = MIN_TRACKING_SAMPLE,
) -> list[dict[str, Any]]:
    """Compare the latest available skill-demand period against the previous one using trusted historical data only."""
    target = Path(skill_history_path) if skill_history_path is not None else GOLD_JOB_POSTINGS_PATH.parent / "skill_demand_trends.csv"
    if not target.exists():
        return []

    date_skill_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    with target.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            date = str(row.get("date") or "").strip()
            skill = str(row.get("skill") or "").strip()
            if not date or not skill:
                continue
            try:
                count = int(float(row.get("job_count") or 0))
            except (TypeError, ValueError):
                continue
            if count <= 0:
                continue
            date_skill_counts[date][skill] += count

    if len(date_skill_counts) < 2:
        return []

    ordered_dates = sorted(date_skill_counts)
    current_date = ordered_dates[-1]
    previous_date = ordered_dates[-2]
    current_counts = date_skill_counts[current_date]
    previous_counts = date_skill_counts[previous_date]
    all_skills = sorted(set(current_counts) | set(previous_counts))

    total_current = sum(current_counts.values())
    rows: list[dict[str, Any]] = []
    for skill in all_skills:
        current_period_jobs = int(current_counts.get(skill, 0))
        previous_period_jobs = int(previous_counts.get(skill, 0))
        if current_period_jobs < min_sample_size and previous_period_jobs < min_sample_size:
            continue
        delta = current_period_jobs - previous_period_jobs
        coverage_pct = (current_period_jobs / total_current * 100.0) if total_current else 0.0
        rows.append(
            {
                "skill": skill,
                "current_period_jobs": current_period_jobs,
                "previous_period_jobs": previous_period_jobs,
                "delta_jobs": delta,
                "delta_pct": round(_safe_pct(delta, previous_period_jobs), 4),
                "sample_size": current_period_jobs,
                "coverage_pct": round(coverage_pct, 4),
                "status": _format_status(delta),
            }
        )
    rows.sort(key=lambda row: (-abs(int(row["delta_jobs"])), str(row["skill"]).casefold()))
    return rows


def _write_csv(path: str | Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return str(output_path)


def write_market_intelligence_outputs(
    *,
    events_dir: str | Path | None = None,
    lifecycle_state_path: str | Path | None = None,
    skill_history_path: str | Path | None = None,
    output_dir: str | Path = GOLD_DATA_DIR,
) -> dict[str, Path]:
    """Generate Gold market-intelligence CSV outputs from existing history and lifecycle records."""
    daily_rows = build_daily_active_job_changes(events_dir)
    weekly_rows = build_weekly_active_job_changes(events_dir)
    company_rows = build_company_movement(events_dir)
    role_rows = build_role_hiring_trends(events_dir)
    skill_rows = build_skill_momentum(skill_history_path)

    output_directory = Path(output_dir)
    output_paths = {
        "daily": Path(_write_csv(output_directory / "market_intelligence_daily.csv", DAILY_FIELDNAMES, daily_rows)),
        "weekly": Path(_write_csv(output_directory / "market_intelligence_weekly.csv", WEEKLY_FIELDNAMES, weekly_rows)),
        "company_movement": Path(_write_csv(output_directory / "company_movement.csv", COMPANY_MOVEMENT_FIELDNAMES, company_rows)),
        "role_hiring_trends": Path(_write_csv(output_directory / "role_hiring_trends.csv", ROLE_TREND_FIELDNAMES, role_rows)),
        "skill_momentum": Path(_write_csv(output_directory / "skill_momentum.csv", SKILL_MOMENTUM_FIELDNAMES, skill_rows)),
    }
    return output_paths


def main() -> int:
    """Generate the Phase 5A market-intelligence Gold outputs."""
    write_market_intelligence_outputs(
        events_dir=INGESTION_JOB_EVENTS_DIR,
        skill_history_path=GOLD_JOB_POSTINGS_PATH.parent / "skill_demand_trends.csv",
        output_dir=GOLD_DATA_DIR,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
