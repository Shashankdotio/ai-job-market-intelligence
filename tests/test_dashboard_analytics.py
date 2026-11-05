"""Tests for gold-backed dashboard filtering and presentation analytics."""

import pandas as pd
import unittest

from dashboard.analytics import (
    DashboardFilters,
    apply_filters,
    classify_seniority,
    classify_work_mode,
    count_by_column,
    enrich_jobs,
    jobs_with_skill,
    skill_frequency,
)
from dashboard.data import HISTORICAL_COLUMNS, load_historical_analytics_data


def _jobs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "company": "acme",
                "title": "Senior AI Engineer",
                "location": "Remote - US",
                "department": "Engineering",
                "skills": '["Python", "LLM"]',
            },
            {
                "company": "beta",
                "title": "Product Manager",
                "location": "Hybrid - New York",
                "department": "Product",
                "skills": '["SQL", "Python"]',
            },
            {
                "company": "acme",
                "title": "VP of Research",
                "location": "San Francisco, CA",
                "department": "Research",
                "skills": "[]",
            },
        ]
    )


class DashboardAnalyticsTests(unittest.TestCase):
    def test_enrichment_classifies_work_arrangement_and_seniority(self) -> None:
        jobs = enrich_jobs(_jobs())

        self.assertEqual(jobs["work_mode"].tolist(), ["Remote", "Hybrid", "Onsite"])
        self.assertEqual(
            jobs["seniority"].tolist(),
            ["Senior", "Mid-level", "Leadership"],
        )
        self.assertEqual(jobs["skill_list"].tolist()[0], ("Python", "LLM"))

    def test_global_filters_intersect_company_skill_work_mode_and_search(self) -> None:
        jobs = enrich_jobs(_jobs())
        filters = DashboardFilters(
            companies=("acme",),
            skills=("Python",),
            work_modes=("Remote",),
            search_query="engineer",
        )

        result = apply_filters(jobs, filters)

        self.assertEqual(result["title"].tolist(), ["Senior AI Engineer"])

    def test_chart_aggregates_derive_from_filtered_gold_jobs(self) -> None:
        jobs = enrich_jobs(_jobs())
        acme_jobs = apply_filters(jobs, DashboardFilters(companies=("acme",)))

        skills = skill_frequency(acme_jobs)
        titles = count_by_column(acme_jobs, "title")
        matching_jobs = jobs_with_skill(jobs, "Python")

        self.assertEqual(
            skills.to_dict("records"),
            [
                {"skill": "Python", "job_count": 1},
                {"skill": "LLM", "job_count": 1},
            ],
        )
        self.assertEqual(len(titles), 2)
        self.assertEqual(matching_jobs["company"].tolist(), ["acme", "beta"])

    def test_classification_helpers_cover_expected_labels(self) -> None:
        self.assertEqual(classify_work_mode("Hybrid - London"), "Hybrid")
        self.assertEqual(classify_work_mode("Toronto, Canada"), "Onsite")
        self.assertEqual(classify_seniority("Director of Engineering"), "Director")
        self.assertEqual(classify_seniority("Data Science Intern"), "Entry")

    def test_historical_analytics_data_has_expected_schema_and_empty_fallbacks(self) -> None:
        historical = load_historical_analytics_data()

        self.assertEqual(
            list(historical["hiring_trends_daily"].columns),
            HISTORICAL_COLUMNS["hiring_trends_daily"],
        )
        self.assertEqual(
            list(historical["hiring_trends_weekly"].columns),
            HISTORICAL_COLUMNS["hiring_trends_weekly"],
        )
        self.assertEqual(
            list(historical["company_activity"].columns),
            HISTORICAL_COLUMNS["company_activity"],
        )
        self.assertEqual(
            list(historical["lifecycle_summary"].columns),
            HISTORICAL_COLUMNS["lifecycle_summary"],
        )
        self.assertEqual(
            list(historical["job_changes"].columns),
            HISTORICAL_COLUMNS["job_changes"],
        )
        self.assertEqual(
            list(historical["skill_demand_trends"].columns),
            HISTORICAL_COLUMNS["skill_demand_trends"],
        )
