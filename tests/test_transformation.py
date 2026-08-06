"""Offline tests for the Milestone 2 bronze, silver, gold, and quality layers."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_job_market.pipeline.transformation import (
    run_quality_check,
    run_transformation,
)


LEGACY_FIELDS = (
    "company",
    "title",
    "location",
    "updated_at",
    "job_url",
    "department",
    "office",
    "description",
)


class TransformationPipelineTests(unittest.TestCase):
    def test_creates_traceable_bronze_silver_gold_and_quality_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "jobs_master.csv"
            self._write_source(source_path)
            quality_path = root / "quality" / "latest_report.json"
            summary = run_transformation(
                source_path=source_path,
                snapshot_id="test_snapshot",
                bronze_snapshots_dir=root / "bronze" / "job_snapshots",
                silver_path=root / "silver" / "job_postings.csv",
                gold_directory=root / "gold",
                quality_report_path=quality_path,
                write_legacy_outputs=False,
            )

            silver_records = self._read_csv(summary.silver_path)
            company_counts = self._read_csv(root / "gold" / "company_counts.csv")
            skill_counts = self._read_csv(root / "gold" / "skill_counts.csv")
            job_postings = self._read_csv(root / "gold" / "job_postings.csv")
            gold_metadata = json.loads(
                (root / "gold" / "metadata.json").read_text(encoding="utf-8")
            )
            quality_report = json.loads(quality_path.read_text(encoding="utf-8"))
            manifest = json.loads(
                (summary.snapshot.path / "manifest.json").read_text(encoding="utf-8")
            )
            snapshot_records_exist = (summary.snapshot.path / "jobs.jsonl").is_file()

        self.assertEqual(summary.snapshot.snapshot_id, "test_snapshot")
        self.assertEqual(manifest["record_count"], 2)
        self.assertEqual(manifest["schema_version"], 1)
        self.assertTrue(snapshot_records_exist)
        self.assertEqual(silver_records[0]["provider"], "greenhouse")
        self.assertEqual(silver_records[0]["external_job_id"], "101")
        self.assertEqual(silver_records[0]["provenance_status"], "inferred")
        self.assertEqual(json.loads(silver_records[0]["skills"]), ["Python", "SQL"])
        self.assertEqual(company_counts, [{"company": "acme", "job_count": "2"}])
        self.assertEqual(skill_counts[0], {"skill": "Python", "job_count": "2"})
        self.assertEqual(job_postings[0]["company"], "acme")
        self.assertNotIn("description", job_postings[0])
        self.assertEqual(gold_metadata["total_jobs"], 2)
        self.assertEqual(gold_metadata["total_skills"], 2)
        self.assertTrue(quality_report["passed"])
        self.assertEqual(quality_report["warning_count"], 2)

    def test_quality_check_reads_existing_silver_without_retransforming(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "jobs_master.csv"
            self._write_source(source_path)
            silver_path = root / "silver" / "job_postings.csv"
            summary = run_transformation(
                source_path=source_path,
                snapshot_id="quality_snapshot",
                bronze_snapshots_dir=root / "bronze" / "job_snapshots",
                silver_path=silver_path,
                gold_directory=root / "gold",
                quality_report_path=root / "quality" / "transform_report.json",
                write_legacy_outputs=False,
            )
            quality_path = root / "quality" / "checked_report.json"
            report = run_quality_check(
                silver_path=summary.silver_path,
                quality_report_path=quality_path,
            )

            persisted = json.loads(quality_path.read_text(encoding="utf-8"))

        self.assertTrue(report.passed)
        self.assertEqual(persisted["record_count"], 2)
        self.assertEqual(persisted["error_count"], 0)

    def test_rejects_duplicate_job_identity_before_silver_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "jobs_master.csv"
            self._write_source(source_path, duplicate_job_url=True)
            silver_path = root / "silver" / "job_postings.csv"
            quality_path = root / "quality" / "latest_report.json"

            with self.assertRaisesRegex(ValueError, "quality failed"):
                run_transformation(
                    source_path=source_path,
                    snapshot_id="duplicate_snapshot",
                    bronze_snapshots_dir=root / "bronze" / "job_snapshots",
                    silver_path=silver_path,
                    gold_directory=root / "gold",
                    quality_report_path=quality_path,
                    write_legacy_outputs=False,
                )

            report = json.loads(quality_path.read_text(encoding="utf-8"))
            silver_exists = silver_path.exists()

        self.assertFalse(silver_exists)
        self.assertFalse(report["passed"])
        self.assertEqual(report["errors"][0]["code"], "duplicate_job_key")

    @staticmethod
    def _write_source(path: Path, duplicate_job_url: bool = False) -> None:
        records = [
            {
                "company": "acme",
                "title": "Machine Learning Engineer",
                "location": "Remote",
                "updated_at": "2026-08-06T00:00:00Z",
                "job_url": "https://job-boards.greenhouse.io/acme/jobs/101",
                "department": "Engineering",
                "office": "Remote",
                "description": "<p>Python and SQL are required.</p>",
            },
            {
                "company": "acme",
                "title": "AI Platform Engineer",
                "location": "New York",
                "updated_at": "2026-08-06T01:00:00Z",
                "job_url": (
                    "https://job-boards.greenhouse.io/acme/jobs/101"
                    if duplicate_job_url
                    else "https://job-boards.greenhouse.io/acme/jobs/102"
                ),
                "department": "Engineering",
                "office": "New York",
                "description": "Python experience is required.",
            },
        ]
        with path.open("w", encoding="utf-8", newline="") as source_file:
            writer = csv.DictWriter(source_file, fieldnames=LEGACY_FIELDS)
            writer.writeheader()
            writer.writerows(records)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source_file:
            return list(csv.DictReader(source_file))
