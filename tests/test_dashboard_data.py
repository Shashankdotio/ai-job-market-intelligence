"""Tests for the dashboard's gold-only read contract."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from dashboard.data_repository import GoldDataUnavailableError, load_gold_data


class GoldDataRepositoryTests(unittest.TestCase):
    def test_loads_only_complete_gold_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gold_directory = Path(directory)
            self._write_gold_contract(gold_directory)

            data = load_gold_data(gold_directory)

        self.assertEqual(data.metadata["total_jobs"], 1)
        self.assertEqual(data.company_counts.iloc[0]["job_count"], 1)
        self.assertEqual(data.job_postings.iloc[0]["title"], "AI Engineer")

    def test_explains_how_to_materialize_missing_gold_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(GoldDataUnavailableError, "transform"):
                load_gold_data(Path(directory))

    @staticmethod
    def _write_gold_contract(gold_directory: Path) -> None:
        GoldDataRepositoryTests._write_csv(
            gold_directory / "company_counts.csv",
            ("company", "job_count"),
            [{"company": "acme", "job_count": 1}],
        )
        GoldDataRepositoryTests._write_csv(
            gold_directory / "skill_counts.csv",
            ("skill", "job_count"),
            [{"skill": "Python", "job_count": 1}],
        )
        GoldDataRepositoryTests._write_csv(
            gold_directory / "company_skill_counts.csv",
            ("company", "skill", "job_count"),
            [{"company": "acme", "skill": "Python", "job_count": 1}],
        )
        GoldDataRepositoryTests._write_csv(
            gold_directory / "job_postings.csv",
            (
                "company",
                "title",
                "location",
                "updated_at",
                "job_url",
                "skills",
            ),
            [
                {
                    "company": "acme",
                    "title": "AI Engineer",
                    "location": "Remote",
                    "updated_at": "2026-08-06T00:00:00Z",
                    "job_url": "https://jobs.example.test/1",
                    "skills": '["Python"]',
                }
            ],
        )
        (gold_directory / "metadata.json").write_text(
            json.dumps({"total_jobs": 1, "generated_at": "2026-08-06T00:00:00Z"}),
            encoding="utf-8",
        )

    @staticmethod
    def _write_csv(
        path: Path,
        fieldnames: tuple[str, ...],
        records: list[dict[str, object]],
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
