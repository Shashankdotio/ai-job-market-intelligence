"""Historical hiring analytics derived from append-only observation and lifecycle history."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_job_market.config import (
    GOLD_COMPANY_ACTIVITY_PATH,
    GOLD_HIRING_TRENDS_DAILY_PATH,
    GOLD_HIRING_TRENDS_WEEKLY_PATH,
    GOLD_JOB_CHANGES_PATH,
    GOLD_LIFECYCLE_SUMMARY_PATH,
    GOLD_SKILL_DEMAND_TRENDS_PATH,
    INGESTION_JOB_EVENTS_DIR,
    INGESTION_JOB_LIFECYCLE_DIR,
    INGESTION_JOB_OBSERVATIONS_DIR,
    JOB_LIFECYCLE_EVENTS_PATH,
    JOB_LIFECYCLE_STATE_PATH,
)
from ai_job_market.etl.io import read_jsonl_records, write_json_atomic


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


def _iter_jsonl_records(path: Path | str) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    records = read_jsonl_records(target)
    return [record for record in records if isinstance(record, dict)]


def _iter_history_files(directory: Path | str) -> list[Path]:
    target = Path(directory)
    if not target.exists():
        return []
    return sorted(p for p in target.glob("*.jsonl") if p.is_file())


def _dedupe_records(records: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for record in records:
        key = tuple(str(record.get(field, "")) for field in key_fields)
        if not any(field for field in key_fields) and not record:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _sorted_rows(rows: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get(key_name, "")))


def _read_event_records(events_dir: Path | str | None = None) -> list[dict[str, Any]]:
    target = Path(events_dir) if events_dir is not None else INGESTION_JOB_EVENTS_DIR
    files = _iter_history_files(target)
    raw_records: list[dict[str, Any]] = []
    for file_path in files:
        raw_records.extend(_iter_jsonl_records(file_path))
    deduped = _dedupe_records(raw_records, ("event_id", "event_type", "company_slug", "external_job_id", "occurred_at"))
    return deduped


def _read_observation_records(observations_dir: Path | str | None = None) -> list[dict[str, Any]]:
    target = Path(observations_dir) if observations_dir is not None else INGESTION_JOB_OBSERVATIONS_DIR
    raw_records: list[dict[str, Any]] = []
    for file_path in _iter_history_files(target):
        raw_records.extend(_iter_jsonl_records(file_path))
    return _dedupe_records(raw_records, ("observation_id", "provider", "company_slug", "external_job_id", "observed_at"))


def build_hiring_trends_daily(
    events_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for record in _read_event_records(events_dir):
        if record.get("event_type") != "discovered":
            continue
        date = _as_iso_date(record.get("occurred_at"))
        if date is None:
            continue
        counts[date] += 1
    return [{"date": date, "job_count": count} for date, count in sorted(counts.items())]


def build_hiring_trends_weekly(
    events_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for record in _read_event_records(events_dir):
        if record.get("event_type") != "discovered":
            continue
        week_start = _as_iso_week(record.get("occurred_at"))
        if week_start is None:
            continue
        counts[week_start] += 1
    return [{"week_start": week_start, "job_count": count} for week_start, count in sorted(counts.items())]


def build_company_activity(
    events_dir: Path | str | None = None,
    lifecycle_state_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    discovered_counts: Counter[str] = Counter()
    closed_counts: Counter[str] = Counter()
    reopened_counts: Counter[str] = Counter()
    active_counts: Counter[str] = Counter()
    suspected_closed_counts: Counter[str] = Counter()

    for record in _read_event_records(events_dir):
        company_slug = str(record.get("company_slug") or "").strip()
        if not company_slug:
            continue
        event_type = str(record.get("event_type") or "")
        if event_type == "discovered":
            discovered_counts[company_slug] += 1
        elif event_type == "closed":
            closed_counts[company_slug] += 1
        elif event_type == "reopened":
            reopened_counts[company_slug] += 1

    state_path = Path(lifecycle_state_path) if lifecycle_state_path is not None else JOB_LIFECYCLE_STATE_PATH
    for record in _iter_jsonl_records(state_path):
        company_slug = str(record.get("company_slug") or "").strip()
        if not company_slug:
            continue
        state = str(record.get("lifecycle_state") or "")
        if state == "active":
            active_counts[company_slug] += 1
        elif state == "suspected_closed":
            suspected_closed_counts[company_slug] += 1
        elif state == "closed":
            closed_counts[company_slug] += 1

    companies = sorted(set(discovered_counts) | set(closed_counts) | set(reopened_counts) | set(active_counts) | set(suspected_closed_counts))
    rows: list[dict[str, Any]] = []
    for company_slug in companies:
        rows.append(
            {
                "company": company_slug,
                "new_jobs": discovered_counts.get(company_slug, 0),
                "closed_jobs": closed_counts.get(company_slug, 0),
                "reopened_jobs": reopened_counts.get(company_slug, 0),
                "current_active_jobs": active_counts.get(company_slug, 0),
                "current_suspected_closed_jobs": suspected_closed_counts.get(company_slug, 0),
            }
        )
    return _sorted_rows(rows, "company")


def build_lifecycle_summary(
    lifecycle_state_path: Path | str | None = None,
    lifecycle_events_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    state_path = Path(lifecycle_state_path) if lifecycle_state_path is not None else JOB_LIFECYCLE_STATE_PATH
    events_path = Path(lifecycle_events_path) if lifecycle_events_path is not None else JOB_LIFECYCLE_EVENTS_PATH

    state_counts: Counter[str] = Counter()
    for record in _iter_jsonl_records(state_path):
        state = str(record.get("lifecycle_state") or "")
        if state:
            state_counts[state] += 1

    event_counts: Counter[str] = Counter()
    for record in _iter_jsonl_records(events_path):
        event_type = str(record.get("event_type") or "")
        if event_type == "reopened":
            event_counts["reopened_jobs"] += 1

    as_of = None
    for record in _iter_jsonl_records(state_path) + _iter_jsonl_records(events_path):
        timestamp = record.get("updated_at") or record.get("occurred_at") or record.get("observed_at")
        candidate = _as_utc(timestamp)
        if candidate is not None and (as_of is None or candidate > as_of):
            as_of = candidate

    rows: list[dict[str, Any]] = [
        {"metric": "active_jobs", "value": state_counts.get("active", 0), "as_of": as_of.isoformat() if as_of else ""},
        {"metric": "suspected_closed_jobs", "value": state_counts.get("suspected_closed", 0), "as_of": as_of.isoformat() if as_of else ""},
        {"metric": "closed_jobs", "value": state_counts.get("closed", 0), "as_of": as_of.isoformat() if as_of else ""},
        {"metric": "reopened_jobs", "value": event_counts.get("reopened_jobs", 0), "as_of": as_of.isoformat() if as_of else ""},
    ]
    return rows


def build_job_changes(events_dir: Path | str | None = None) -> list[dict[str, Any]]:
    daily_updates: dict[str, set[str]] = defaultdict(set)
    daily_counts: Counter[str] = Counter()

    for record in _read_event_records(events_dir):
        if record.get("event_type") != "updated":
            continue
        event_date = _as_iso_date(record.get("occurred_at"))
        if event_date is None:
            continue
        key = str(record.get("job_key") or record.get("external_job_id") or record.get("event_id") or "unknown")
        daily_updates[event_date].add(key)
        daily_counts[event_date] += 1

    rows: list[dict[str, Any]] = []
    for event_date in sorted(daily_counts):
        rows.append(
            {
                "event_date": event_date,
                "update_count": daily_counts[event_date],
                "unique_jobs_updated": len(daily_updates[event_date]),
            }
        )
    return rows


def build_skill_demand_trends(observations_dir: Path | str | None = None) -> list[dict[str, Any]]:
    observations = _read_observation_records(observations_dir)
    records_with_skills = []
    for record in observations:
        skills = record.get("skills")
        if skills is None:
            continue
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except json.JSONDecodeError:
                continue
        if isinstance(skills, list) and skills and all(isinstance(skill, str) for skill in skills):
            records_with_skills.append((record, skills))

    if not records_with_skills:
        return []

    aggregate: dict[str, Counter[str]] = defaultdict(Counter)
    for record, skills in records_with_skills:
        date = _as_iso_date(record.get("observed_at") or record.get("created_at"))
        if date is None:
            continue
        for skill in skills:
            aggregate[date][skill.strip()] += 1

    rows: list[dict[str, Any]] = []
    for date in sorted(aggregate):
        for skill, count in sorted(aggregate[date].items()):
            rows.append({"date": date, "skill": skill, "job_count": count})
    return rows


def write_historical_analytics(
    observations_dir: Path | str | None = None,
    events_dir: Path | str | None = None,
    lifecycle_state_path: Path | str | None = None,
    lifecycle_events_path: Path | str | None = None,
    output_dir: Path | str | None = None,
) -> dict[str, Path]:
    target_dir = Path(output_dir) if output_dir is not None else Path(GOLD_HIRING_TRENDS_DAILY_PATH).parent
    target_dir.mkdir(parents=True, exist_ok=True)

    datasets = {
        "hiring_trends_daily": build_hiring_trends_daily(events_dir),
        "hiring_trends_weekly": build_hiring_trends_weekly(events_dir),
        "company_activity": build_company_activity(events_dir, lifecycle_state_path),
        "lifecycle_summary": build_lifecycle_summary(lifecycle_state_path, lifecycle_events_path),
        "job_changes": build_job_changes(events_dir),
        "skill_demand_trends": build_skill_demand_trends(observations_dir),
    }

    output_paths = {
        "hiring_trends_daily": target_dir / "hiring_trends_daily.csv",
        "hiring_trends_weekly": target_dir / "hiring_trends_weekly.csv",
        "company_activity": target_dir / "company_activity.csv",
        "lifecycle_summary": target_dir / "lifecycle_summary.csv",
        "job_changes": target_dir / "job_changes.csv",
        "skill_demand_trends": target_dir / "skill_demand_trends.csv",
    }

    for name, rows in datasets.items():
        path = output_paths[name]
        fieldnames: list[str] = []
        if name == "hiring_trends_daily":
            fieldnames = ["date", "job_count"]
        elif name == "hiring_trends_weekly":
            fieldnames = ["week_start", "job_count"]
        elif name == "company_activity":
            fieldnames = ["company", "new_jobs", "closed_jobs", "reopened_jobs", "current_active_jobs", "current_suspected_closed_jobs"]
        elif name == "lifecycle_summary":
            fieldnames = ["metric", "value", "as_of"]
        elif name == "job_changes":
            fieldnames = ["event_date", "update_count", "unique_jobs_updated"]
        elif name == "skill_demand_trends":
            fieldnames = ["date", "skill", "job_count"]

        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    return output_paths


def main() -> int:
    write_historical_analytics(
        observations_dir=INGESTION_JOB_OBSERVATIONS_DIR,
        events_dir=INGESTION_JOB_EVENTS_DIR,
        lifecycle_state_path=JOB_LIFECYCLE_STATE_PATH,
        lifecycle_events_path=JOB_LIFECYCLE_EVENTS_PATH,
        output_dir=Path(GOLD_HIRING_TRENDS_DAILY_PATH).parent,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
