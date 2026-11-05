"""Unit tests for skill co-occurrence analytics."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_job_market.skill_cooccurrence import (
    build_skill_cooccurrence,
    build_skill_frequency,
    write_skill_cooccurrence_outputs,
)


class SkillCooccurrenceTests(unittest.TestCase):
    def test_skill_frequency_counts_each_skill_once_per_job(self) -> None:
        records = [
            {"skills": json.dumps(["Python", "python", "SQL"])},
            {"skills": json.dumps(["PYTHON", "LLM"])},
            {"skills": "[]"},
        ]

        result = build_skill_frequency(records)

        self.assertEqual(
            sorted((row["skill"], row["job_count"]) for row in result),
            [("LLM", 1), ("Python", 2), ("SQL", 1)],
        )

    def test_pair_counts_conditional_percentages_and_jaccard_similarity(self) -> None:
        records = [
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL", "LLM"])},
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "LLM"])},
            {"company": "beta", "title": "Analyst", "skills": json.dumps(["SQL", "Python"])},
            {"company": "gamma", "title": "Scientist", "skills": json.dumps(["AWS", "SQL"])},
        ]

        rows = build_skill_cooccurrence(records, min_cooccurrence=1)
        pair = next(row for row in rows if row["skill_a"] == "Python" and row["skill_b"] == "SQL")

        self.assertEqual(pair["pair_count"], 2)
        self.assertEqual(pair["skill_a_count"], 3)
        self.assertEqual(pair["skill_b_count"], 3)
        self.assertAlmostEqual(pair["pct_b_given_a"], 66.6667, places=4)
        self.assertAlmostEqual(pair["pct_a_given_b"], 66.6667, places=4)
        self.assertAlmostEqual(pair["jaccard_similarity"], 0.5, places=4)

    def test_reverse_conditional_percentage_uses_unequal_skill_frequencies(self) -> None:
        records = [
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"company": "beta", "title": "Analyst", "skills": json.dumps(["Python", "Azure"])},
        ]

        rows = build_skill_cooccurrence(records, min_cooccurrence=1)
        pair = next(row for row in rows if row["skill_a"] == "Python" and row["skill_b"] == "SQL")

        self.assertAlmostEqual(pair["pct_b_given_a"], 66.6667, places=4)
        self.assertAlmostEqual(pair["pct_a_given_b"], 100.0, places=4)

    def test_cooccurrence_respects_minimum_threshold_and_dedups_duplicates(self) -> None:
        records = [
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "LLM"])},
        ]

        rows = build_skill_cooccurrence(records, min_cooccurrence=2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["skill_a"], "Python")
        self.assertEqual(rows[0]["skill_b"], "SQL")
        self.assertEqual(rows[0]["pair_count"], 2)

        rare_rows = build_skill_cooccurrence(records, min_cooccurrence=3)
        self.assertEqual(rare_rows, [])

    def test_grouped_cooccurrence_tracks_by_company_and_title(self) -> None:
        records = [
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"company": "acme", "title": "Scientist", "skills": json.dumps(["Python", "LLM"])},
            {"company": "beta", "title": "Engineer", "skills": json.dumps(["SQL", "Python"])},
            {"company": "beta", "title": "Analyst", "skills": json.dumps(["AWS", "SQL"])},
        ]

        company_rows = build_skill_cooccurrence(records, group_by="company", min_cooccurrence=1)
        title_rows = build_skill_cooccurrence(records, group_by="title", min_cooccurrence=1)

        self.assertTrue(any(row["company"] == "acme" and row["skill_a"] == "Python" and row["skill_b"] == "SQL" for row in company_rows))
        self.assertTrue(any(row["title"] == "Engineer" and row["skill_a"] == "Python" and row["skill_b"] == "SQL" for row in title_rows))

    def test_empty_dataset_writes_header_only_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            paths = write_skill_cooccurrence_outputs([], output_dir=output_dir, min_cooccurrence=2)

            for path in paths.values():
                with path.open("r", newline="", encoding="utf-8") as handle:
                    rows = list(csv.reader(handle))
                self.assertEqual(len(rows), 1)
                self.assertEqual(
                    rows[0],
                    [
                        "skill_a",
                        "skill_b",
                        "pair_count",
                        "skill_a_count",
                        "skill_b_count",
                        "pct_b_given_a",
                        "pct_a_given_b",
                        "jaccard_similarity",
                    ],
                )

    def test_write_outputs_uses_expected_schema(self) -> None:
        records = [
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "SQL", "LLM"])},
            {"company": "acme", "title": "Engineer", "skills": json.dumps(["Python", "LLM"])},
            {"company": "beta", "title": "Analyst", "skills": json.dumps(["SQL", "Python"])},
        ]

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            paths = write_skill_cooccurrence_outputs(records, output_dir=output_dir, min_cooccurrence=1)

            self.assertTrue(paths["overall"].exists())
            self.assertTrue(paths["by_company"].exists())
            self.assertTrue(paths["by_title"].exists())
            with paths["overall"].open("r", newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("pct_b_given_a", rows[0])
            self.assertIn("pct_a_given_b", rows[0])
            self.assertIn("jaccard_similarity", rows[0])


if __name__ == "__main__":
    unittest.main()
