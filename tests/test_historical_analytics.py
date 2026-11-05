import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_job_market.historical_analytics import (
    build_company_activity,
    build_hiring_trends_daily,
    build_hiring_trends_weekly,
    build_job_changes,
    build_lifecycle_summary,
    build_skill_demand_trends,
    write_historical_analytics,
)


def _write_jsonl(path: Path, records):
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")


class HistoricalAnalyticsTests(unittest.TestCase):
    def test_historical_analytics_groups_daily_and_weekly_discovery_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            events_dir = base / "events"
            events_dir.mkdir()

            discovered = [
                {"event_id": "1", "event_type": "discovered", "company_slug": "alpha", "occurred_at": "2026-08-03T10:00:00+00:00"},
                {"event_id": "2", "event_type": "discovered", "company_slug": "alpha", "occurred_at": "2026-08-03T11:00:00+00:00"},
                {"event_id": "3", "event_type": "discovered", "company_slug": "beta", "occurred_at": "2026-08-05T09:00:00+00:00"},
                {"event_id": "4", "event_type": "updated", "company_slug": "alpha", "job_key": "job-1", "occurred_at": "2026-08-03T12:00:00+00:00"},
            ]
            _write_jsonl(events_dir / "history.jsonl", discovered)

            daily = build_hiring_trends_daily(events_dir)
            weekly = build_hiring_trends_weekly(events_dir)
            changes = build_job_changes(events_dir)

            self.assertEqual(daily, [{"date": "2026-08-03", "job_count": 2}, {"date": "2026-08-05", "job_count": 1}])
            self.assertEqual(weekly, [{"week_start": "2026-08-03", "job_count": 3}])
            self.assertEqual(changes, [{"event_date": "2026-08-03", "update_count": 1, "unique_jobs_updated": 1}])

    def test_empty_history_returns_empty_structures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            empty_events_dir = base / "events"
            empty_events_dir.mkdir()
            empty_state_path = base / "lifecycle_state.jsonl"
            empty_events_path = base / "lifecycle_events.jsonl"

            self.assertEqual(build_hiring_trends_daily(empty_events_dir), [])
            self.assertEqual(build_hiring_trends_weekly(empty_events_dir), [])
            self.assertEqual(build_company_activity(empty_events_dir, empty_state_path), [])
            self.assertEqual(
                build_lifecycle_summary(empty_state_path, empty_events_path),
                [
                    {"metric": "active_jobs", "value": 0, "as_of": ""},
                    {"metric": "suspected_closed_jobs", "value": 0, "as_of": ""},
                    {"metric": "closed_jobs", "value": 0, "as_of": ""},
                    {"metric": "reopened_jobs", "value": 0, "as_of": ""},
                ],
            )
            self.assertEqual(build_job_changes(empty_events_dir), [])
            self.assertEqual(build_skill_demand_trends(base / "observations"), [])

    def test_duplicate_events_are_deduplicated_before_aggregation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            events_dir = base / "events"
            events_dir.mkdir()
            records = [
                {"event_id": "dup-1", "event_type": "discovered", "company_slug": "alpha", "occurred_at": "2026-08-04T10:00:00+00:00"},
                {"event_id": "dup-1", "event_type": "discovered", "company_slug": "alpha", "occurred_at": "2026-08-04T10:00:00+00:00"},
                {"event_id": "dup-2", "event_type": "closed", "company_slug": "alpha", "occurred_at": "2026-08-05T11:00:00+00:00"},
            ]
            _write_jsonl(events_dir / "jobs.jsonl", records)

            self.assertEqual(build_hiring_trends_daily(events_dir), [{"date": "2026-08-04", "job_count": 1}])
            self.assertEqual(
                build_company_activity(events_dir, base / "state.jsonl"),
                [{"company": "alpha", "new_jobs": 1, "closed_jobs": 1, "reopened_jobs": 0, "current_active_jobs": 0, "current_suspected_closed_jobs": 0}],
            )

    def test_skill_demand_trends_are_empty_without_reliable_skill_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            obs_dir = base / "observations"
            obs_dir.mkdir()
            _write_jsonl(
                obs_dir / "jobs.jsonl",
                [
                    {"observation_id": "obs-1", "provider": "test", "company_slug": "alpha", "external_job_id": "job-1", "observed_at": "2026-08-04T10:00:00+00:00", "skill_signature": "abc123"},
                ],
            )
            self.assertEqual(build_skill_demand_trends(obs_dir), [])

    def test_write_historical_analytics_writes_expected_csv_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            observations_dir = base / "observations"
            observations_dir.mkdir()
            events_dir = base / "events"
            events_dir.mkdir()
            state_path = base / "lifecycle_state.jsonl"
            events_path = base / "lifecycle_events.jsonl"

            _write_jsonl(
                observations_dir / "jobs.jsonl",
                [{"observation_id": "1", "provider": "acme", "company_slug": "alpha", "external_job_id": "job-1", "observed_at": "2026-08-04T09:00:00+00:00"}],
            )
            _write_jsonl(
                events_dir / "history.jsonl",
                [
                    {"event_id": "d-1", "event_type": "discovered", "company_slug": "alpha", "occurred_at": "2026-08-04T09:00:00+00:00"},
                    {"event_id": "u-1", "event_type": "updated", "company_slug": "alpha", "job_key": "job-1", "occurred_at": "2026-08-04T12:00:00+00:00"},
                ],
            )
            _write_jsonl(
                state_path,
                [{"company_slug": "alpha", "external_job_id": "job-1", "lifecycle_state": "active", "updated_at": "2026-08-04T12:30:00+00:00"}],
            )
            _write_jsonl(
                events_path,
                [{"event_id": "r-1", "event_type": "reopened", "company_slug": "alpha", "occurred_at": "2026-08-05T10:00:00+00:00"}],
            )

            output_paths = write_historical_analytics(
                observations_dir=observations_dir,
                events_dir=events_dir,
                lifecycle_state_path=state_path,
                lifecycle_events_path=events_path,
                output_dir=base / "gold",
            )

            for path in output_paths.values():
                self.assertTrue(path.exists())

            with output_paths["hiring_trends_daily"].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [{"date": "2026-08-04", "job_count": "1"}])

            with output_paths["skill_demand_trends"].open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [])
