"""Reusable Streamlit tables for job-posting details."""

import pandas as pd
import streamlit as st


JOB_TABLE_COLUMNS = (
    "title",
    "company",
    "location",
    "work_mode",
    "department",
    "seniority",
    "updated_at",
    "job_url",
)


def render_jobs_table(
    jobs: pd.DataFrame,
    *,
    empty_message: str,
    max_rows: int = 100,
) -> None:
    """Render a consistently formatted, compact job-postings table."""
    if jobs.empty:
        st.info(empty_message)
        return

    available_columns = [column for column in JOB_TABLE_COLUMNS if column in jobs]
    table = jobs.loc[:, available_columns].head(max_rows).copy()
    table["updated_at"] = pd.to_datetime(
        table["updated_at"], errors="coerce", utc=True
    ).dt.strftime("%Y-%m-%d")
    table = table.rename(
        columns={
            "title": "Title",
            "company": "Company",
            "location": "Location",
            "work_mode": "Work mode",
            "department": "Department",
            "seniority": "Seniority",
            "updated_at": "Updated",
            "job_url": "Job URL",
        }
    )
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Job URL": st.column_config.LinkColumn(
                "Job posting",
                display_text="View job",
            )
        },
    )
    if len(jobs) > max_rows:
        st.caption(f"Showing the first {max_rows:,} of {len(jobs):,} jobs.")
