"""Reusable baseline skill extraction for the current analytics contract."""

import re
from collections.abc import Sequence


SKILLS: tuple[str, ...] = (
    "Python",
    "SQL",
    "R",
    "Java",
    "Scala",
    "C++",
    "JavaScript",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Linux",
    "Git",
    "Spark",
    "Hadoop",
    "Airflow",
    "Kafka",
    "Snowflake",
    "Databricks",
    "dbt",
    "TensorFlow",
    "PyTorch",
    "Scikit-learn",
    "XGBoost",
    "LangChain",
    "LangGraph",
    "OpenAI",
    "LLM",
    "RAG",
    "Vector Database",
    "FAISS",
    "Pinecone",
    "Tableau",
    "Power BI",
    "Excel",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
)


def extract_skills(text: str, skills: Sequence[str] = SKILLS) -> list[str]:
    """Extract configured baseline skills using the project's legacy matcher."""
    return [
        skill
        for skill in skills
        if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE)
    ]
