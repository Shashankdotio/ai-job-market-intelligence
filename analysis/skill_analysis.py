import pandas as pd
from collections import Counter
import matplotlib.pyplot as plt
import ast

# -----------------------------
# Load Processed Dataset
# -----------------------------

df = pd.read_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/jobs_with_skills.csv"
)

print(f"Dataset Shape: {df.shape}")

# -----------------------------
# Convert string back to list
# -----------------------------

df["skills"] = df["skills"].apply(ast.literal_eval)

# -----------------------------
# Flatten all skills
# -----------------------------

all_skills = []

for skills in df["skills"]:
    all_skills.extend(skills)

# -----------------------------
# Count Skills
# -----------------------------

skill_counts = Counter(all_skills)

skill_df = pd.DataFrame(
    skill_counts.most_common(),
    columns=["Skill", "Count"]
)

print(skill_df.head())

# -----------------------------
# Save CSV
# -----------------------------

skill_df.to_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/skill_counts.csv",
    index=False
)

# -----------------------------
# Visualization
# -----------------------------

top10 = skill_df.head(10)

plt.figure(figsize=(10,6))

plt.barh(top10["Skill"], top10["Count"])

plt.gca().invert_yaxis()

plt.title("Top 10 Most Requested Skills")

plt.xlabel("Number of Job Mentions")

plt.ylabel("Skill")

plt.tight_layout()

plt.savefig(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/outputs/charts/top10_skills.png",
    dpi=300
)

plt.show()