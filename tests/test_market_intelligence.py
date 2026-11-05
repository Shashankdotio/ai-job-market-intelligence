"""Tests for Phase 5A market-intelligence analytics."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_job_market.market_intelligence import (
    build_company_movement,
    build_daily_active_job_changes,
    build_role_hiring_trends,
    build_skill_momentum,
    build_weekly_active_job_changes,
    write_market_intelligence_outputs,
)


def _write_jsonl(path: Path, records):
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")


class MarketIntelligenceTests(unittest.TestCase):
    def test_daily_and_weekly_active_job_windows_compare_previous_periods(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            events_dir = base / "events"
            events_dir.mkdir()
            _write_jsonl(
                events_dir / "history.jsonl",
                [
                    {"event_id": "e1", "event_type": "discovered", "company_slug": "alpha", "external_job_id": "j1", "job_key": "alpha:j1", "occurred_at": "2026-08-03T09:00:00+00:00"},
                    {"event_id": "e2", "event_type": "discovered", "company_slug": "alpha", "external_job_id": "j2", "job_key": "alpha:j2", "occurred_at": "2026-08-03T11:00:00+00:00"},
                    {"event_id": "e3", "event_type": "closed", "company_slug": "alpha", "external_job_id": "j1", "job_key": "alpha:j1", "occurred_at": "2026-08-04T09:00:00+00:00"},
                    {"event_id": "e4", "event_type": "reopened", "company_slug": "alpha", "external_job_id": "j1", "job_key": "alpha:j1", "occurred_at": "2026-08-05T10:00:00+00:00"},
                ],
            )

            daily = build_daily_active_job_changes(events_dir)
            weekly = build_weekly_active_job_changes(events_dir)

            self.assertEqual(daily[0]["active_jobs"], 2)
            self.assertEqual(daily[1]["delta_active_jobs"], -1)
            self.assertEqual(daily[-1]["previous_period_active_jobs"], 1)
            self.assertEqual(weekly[0]["week_start"], "2026-08-03")
            self.assertEqual(weekly[0]["active_jobs"], 2)

    def test_company_movement_detects_increasing_and_decreasing_activity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            events_dir = base / "events"
            events_dir.mkdir()
            _write_jsonl(
                events_dir / "history.jsonl",
                [
                    {"event_id": "a1", "event_type": "discovered", "company_slug": "alpha", "external_job_id": "j1", "job_key": "alpha:j1", "occurred_at": "2026-08-03T09:00:00+00:00"},
                    {"event_id": "a2", "event_type": "discovered", "company_slug": "alpha", "external_job_id": "j2", "job_key": "alpha:j2", "occurred_at": "2026-08-05T09:00:00+00:00"},
                    {"event_id": "b1", "event_type": "discovered", "company_slug": "beta", "external_job_id": "j3", "job_key": "beta:j3", "occurred_at": "2026-08-03T09:00:00+00:00"},
                    {"event_id": "b2", "event_type": "closed", "company_slug": "beta", "external_job_id": "j3", "job_key": "beta:j3", "occurred_at": "2026-08-05T09:00:00+00:00"},
                ],
            )

            movement = build_company_movement(events_dir)
            alpha = next(row for row in movement if row["company"] == "alpha")
            beta = next(row for row in movement if row["company"] == "beta")

            self.assertEqual(alpha["status"], "increasing")
            self.assertEqual(beta["status"], "decreasing")

    def test_role_hiring_trends_use_title_taxonomy_and_compare_previous_periods(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            events_dir = base / "events"
            events_dir.mkdir()
            _write_jsonl(
                events_dir / "history.jsonl",
                [
                    {"event_id": "r1", "event_type": "discovered", "company_slug": "alpha", "title": "Machine Learning Engineer", "occurred_at": "2026-08-03T09:00:00+00:00"},
                    {"event_id": "r2", "event_type": "discovered", "company_slug": "alpha", "title": "Machine Learning Engineer", "occurred_at": "2026-08-04T09:00:00+00:00"},
                    {"event_id": "r3", "event_type": "discovered", "company_slug": "alpha", "title": "Machine Learning Engineer", "occurred_at": "2026-08-04T10:00:00+00:00"},
                    {"event_id": "r4", "event_type": "discovered", "company_slug": "alpha", "title": "Software Engineer", "occurred_at": "2026-08-04T11:00:00+00:00"},
                ],
            )

            trends = build_role_hiring_trends(events_dir)
            ml_rows = [row for row in trends if row["role"] == "ML Engineer"]
            self.assertTrue(ml_rows)
            self.assertEqual(ml_rows[0]["role_count"], 1)
            self.assertEqual(ml_rows[0]["previous_period_role_count"], 0)
            self.assertEqual(ml_rows[-1]["delta_count"], 1)

    def test_skill_momentum_requires_reliable_history_and_sparse_data_is_filtered(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            history_path = base / "skill_demand_trends.csv"
            with history_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "skill", "job_count"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-08-01", "skill": "Python", "job_count": 5},
                        {"date": "2026-08-08", "skill": "Python", "job_count": 12},
                        {"date": "2026-08-08", "skill": "SQL", "job_count": 1},
                    ]
                )
            momentum = build_skill_momentum(history_path, min_sample_size=2)
            self.assertEqual(momentum[0]["skill"], "Python")
            self.assertGreater(momentum[0]["delta_jobs"], 0)

            empty = build_skill_momentum(base / "missing.csv")
            self.assertEqual(empty, [])

    def test_write_market_intelligence_outputs_is_repeatable_and_uses_expected_schemas(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            events_dir = base / "events"
            events_dir.mkdir()
            history_path = base / "skill_demand_trends.csv"
            _write_jsonl(
                events_dir / "history.jsonl",
                [
                    {"event_id": "d1", "event_type": "discovered", "company_slug": "alpha", "external_job_id": "j1", "job_key": "alpha:j1", "title": "Machine Learning Engineer", "occurred_at": "2026-08-03T10:00:00+00:00"},
                    {"event_id": "d2", "event_type": "discovered", "company_slug": "alpha", "external_job_id": "j2", "job_key": "alpha:j2", "title": "Software Engineer", "occurred_at": "2026-08-04T10:00:00+00:00"},
                    {"event_id": "c1", "event_type": "closed", "company_slug": "alpha", "external_job_id": "j1", "job_key": "alpha:j1", "occurred_at": "2026-08-05T10:00:00+00:00"},
                ],
            )
            with history_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "skill", "job_count"])
                writer.writeheader()
                writer.writerows(
                    [
                        {"date": "2026-08-01", "skill": "Python", "job_count": 4},
                        {"date": "2026-08-08", "skill": "Python", "job_count": 7},
                    ]
                )

            first = write_market_intelligence_outputs(events_dir=events_dir, skill_history_path=history_path, output_dir=base / "gold")
            second = write_market_intelligence_outputs(events_dir=events_dir, skill_history_path=history_path, output_dir=base / "gold")

            for key in first:
                self.assertTrue(first[key].exists())
                self.assertEqual(first[key].read_bytes(), second[key].read_bytes())

            with (base / "gold" / "market_intelligence_daily.csv").open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("delta_active_jobs", rows[0])


if __name__ == "__main__":
    unittest.main()
