"""Tests for the dashboard's gold-only read contract."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from dashboard.data import load_skill_cooccurrence_data
from dashboard.data_repository import GoldDataUnavailableError, load_gold_data
from dashboard.pages.skills import filter_skill_pairs


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

    def test_skill_cooccurrence_data_loads_with_empty_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            gold_directory = Path(directory)
            (gold_directory / "skill_cooccurrence.csv").write_text(
                "skill_a,skill_b,pair_count,skill_a_count,skill_b_count,pct_b_given_a,pct_a_given_b,jaccard_similarity\n"
                "Python,SQL,5,10,7,100.0,71.4286,0.5\n",
                encoding="utf-8",
            )
            (gold_directory / "skill_cooccurrence_by_company.csv").write_text(
                "company,skill_a,skill_b,pair_count,skill_a_count,skill_b_count,pct_b_given_a,pct_a_given_b,jaccard_similarity\n"
                "acme,Python,SQL,5,10,7,100.0,71.4286,0.5\n",
                encoding="utf-8",
            )
            frames = load_skill_cooccurrence_data(gold_directory)

        self.assertIn("overall", frames)
        self.assertIn("by_company", frames)
        self.assertEqual(frames["overall"].iloc[0]["skill_a"], "Python")
        self.assertEqual(frames["by_company"].iloc[0]["company"], "acme")

    def test_skill_pair_filters_respect_threshold_and_skill_focus(self) -> None:
        pairs = {
            "skill_a": ["Python", "Python", "AWS", "SQL"],
            "skill_b": ["SQL", "AWS", "SQL", "LLM"],
            "pair_count": [4, 2, 1, 3],
        }
        frame = __import__("pandas").DataFrame(pairs)

        filtered = filter_skill_pairs(frame, min_threshold=2, selected_skill="Python")
        self.assertEqual(filtered["pair_count"].tolist(), [4, 2])

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
