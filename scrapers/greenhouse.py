import requests
import pandas as pd
import sys
import os
from bs4 import BeautifulSoup
import html

sys.path.append(os.path.dirname(__file__))

from companies import GREENHOUSE_COMPANIES


from bs4 import BeautifulSoup
import html


def clean_html(text):
    if not text:
        return ""

    # Convert &lt;div&gt; → <div>
    decoded = html.unescape(text)

    # Remove HTML tags
    soup = BeautifulSoup(decoded, "html.parser")

    return soup.get_text(separator=" ", strip=True)


def fetch_jobs(company):

    url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs"

    response = requests.get(url)

    if response.status_code != 200:
        print(f"Failed: {company}")
        return []

    data = response.json()

    jobs = []

    total_jobs = len(data["jobs"])

    for i, job in enumerate(data["jobs"], start=1):

        print(
            f"{company}: {i}/{total_jobs}",
            end="\r"
        )

        job_id = job["id"]

        detail_url = (
            f"https://boards-api.greenhouse.io/v1/boards/"
            f"{company}/jobs/{job_id}"
        )

        detail_response = requests.get(detail_url)

        if detail_response.status_code != 200:
            continue

        detail = detail_response.json()

        description = clean_html(
            detail.get("content", "")
        )

        departments = ", ".join(
            dept.get("name", "")
            for dept in detail.get("departments", [])
        )

        offices = ", ".join(
            office.get("name", "")
            for office in detail.get("offices", [])
        )

        jobs.append({
            "company": company,
            "title": job.get("title"),
            "location": job.get("location", {}).get("name"),
            "updated_at": job.get("updated_at"),
            "job_url": job.get("absolute_url"),
            "department": departments,
            "office": offices,
            "description": description
        })

    print(f"\nCompleted {company}")

    return jobs


all_jobs = []

for company in GREENHOUSE_COMPANIES:

    print(f"\nFetching {company}")

    jobs = fetch_jobs(company)

    print(f"Found {len(jobs)} jobs")

    all_jobs.extend(jobs)

df = pd.DataFrame(all_jobs)

print(f"\nTotal Jobs Collected: {len(df)}")

os.makedirs("data", exist_ok=True)

df.to_csv(
    "data/jobs_master.csv",
    index=False
)

print("\nSaved to data/jobs_master.csv")