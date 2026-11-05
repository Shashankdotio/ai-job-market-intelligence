"""Tests for deterministic role-based skill intelligence."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from ai_job_market.role_skill_intelligence import (
    build_role_skill_counts,
    build_role_skill_summary,
    classify_role,
    write_role_skill_outputs,
)


class RoleSkillIntelligenceTests(unittest.TestCase):
    def test_classify_role_uses_deterministic_keyword_rules(self) -> None:
        self.assertEqual(classify_role("Machine Learning Engineer"), "ML Engineer")
        self.assertEqual(classify_role("AI Engineer, LLM Systems"), "AI Engineer")
        self.assertEqual(classify_role("Data Scientist - Applied ML"), "Data Scientist")
        self.assertEqual(classify_role("Product Manager"), "Other/Unclassified")

    def test_role_outputs_exclude_sparse_roles_and_dedupe_skills_per_posting(self) -> None:
        records = [
            {"title": "Machine Learning Engineer", "skills": json.dumps(["Python", "Python", "SQL", "LLM"])},
            {"title": "Machine Learning Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"title": "Machine Learning Engineer", "skills": json.dumps(["Python", "AWS"])},
            {"title": "Machine Learning Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"title": "Machine Learning Engineer", "skills": json.dumps(["Python", "SQL"])},
            {"title": "Software Engineer", "skills": json.dumps(["JavaScript", "SQL"])},
        ]

        summary = build_role_skill_summary(records)
        summary_by_role = {row["role"]: row for row in summary}
        self.assertGreaterEqual(summary_by_role["ML Engineer"]["posting_count"], 5)
        self.assertEqual(summary_by_role["Software Engineer"]["posting_count"], 1)

        counts = build_role_skill_counts(records, min_role_postings=5)
        role_counts = {row["skill"]: row for row in counts if row["role"] == "ML Engineer"}
        self.assertEqual(role_counts["Python"]["skill_count"], 5)
        self.assertEqual(role_counts["SQL"]["skill_count"], 4)

    def test_empty_dataset_writes_header_only_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            paths = write_role_skill_outputs([], output_dir=output_dir, min_role_postings=5)
            for path in paths.values():
                with path.open("r", newline="", encoding="utf-8") as handle:
                    rows = list(csv.reader(handle))
                self.assertEqual(len(rows), 1)
                self.assertIn("role", rows[0])


if __name__ == "__main__":
    unittest.main()
