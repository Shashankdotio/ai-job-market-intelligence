import pandas as pd
import re
from bs4 import BeautifulSoup
import html
from collections import Counter
import matplotlib.pyplot as plt

def clean_html(text):
    if pd.isna(text):
        return ""

    decoded = html.unescape(text)

    soup = BeautifulSoup(decoded, "html.parser")

    return soup.get_text(separator=" ", strip=True)

def extract_skills(text):
    found_skills = []

    for skill in SKILLS:
        if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE):
            found_skills.append(skill)

    return found_skills


SKILLS = [
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
    "MongoDB"
]

df = pd.read_csv("/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/raw/jobs_master.csv")
df["clean_description"] = df["description"].apply(clean_html)
df["skills"] = df["clean_description"].apply(extract_skills)

df.to_csv(

    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/jobs_with_skills.csv",

    index=False

)

print("Saved jobs_with_skills.csv")

all_skills = []

for skills in df["skills"]:
    all_skills.extend(skills)

skill_counts = Counter(all_skills) 


skill_df = pd.DataFrame(

    skill_counts.most_common(),

    columns=["Skill", "Count"]

)
print(skill_df.head(10))
skill_df.to_csv("/Users/shashank/Documents/Projects/ai-job-market-dashboard/outputs/skill_counts.csv", index=False)


'''

top10 = skill_df.head(10)
plt.figure(figsize=(10, 6))

plt.barh(top10["Skill"], top10["Count"])
plt.gca().invert_yaxis()

plt.xlabel("Number of Job Mentions")
plt.ylabel("Skill")

plt.title("Top 10 Most Requested Skills")

plt.savefig("/Users/shashank/Documents/Projects/ai-job-market-dashboard/outputs/top10_skills.png", dpi=300, bbox_inches="tight")
plt.show()
'''