import pandas as pd
import ast
import matplotlib.pyplot as plt

# --------------------------------------------------
# Load Processed Dataset
# --------------------------------------------------

df = pd.read_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/jobs_with_skills.csv"
)

# Convert string representation of list back into actual Python list
df["skills"] = df["skills"].apply(ast.literal_eval)

print(f"Dataset Shape: {df.shape}")
print()

# --------------------------------------------------
# Explode Skills
# --------------------------------------------------

company_skills = df.explode("skills")

# Remove rows where no skill was extracted
company_skills = company_skills.dropna(subset=["skills"])

print("Exploded Data:")
print(company_skills[["company", "skills"]].head())
print()

# --------------------------------------------------
# Count Skills per Company
# --------------------------------------------------

company_skill_counts = (
    company_skills
    .groupby(["company", "skills"])
    .size()
    .reset_index(name="Count")
)

# Sort companies alphabetically,
# then show most common skills first
company_skill_counts = company_skill_counts.sort_values(
    by=["company", "Count"],
    ascending=[True, False]
)

print("Company Skill Counts:")
print(company_skill_counts.head(20))
print()

# --------------------------------------------------
# Save Dataset
# --------------------------------------------------

company_skill_counts.to_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/company_skill_counts.csv",
    index=False
)

print("Saved company_skill_counts.csv")

# --------------------------------------------------
# Visualization
# --------------------------------------------------

# Get Top 10 company-skill combinations
top10 = company_skill_counts.sort_values(
    by="Count",
    ascending=False
).head(10)

# Create labels like "Anthropic - Python"
top10["Label"] = top10["company"] + " - " + top10["skills"]

plt.figure(figsize=(12, 6))

plt.barh(top10["Label"], top10["Count"])

plt.gca().invert_yaxis()

plt.title("Top Company-Skill Combinations")

plt.xlabel("Number of Job Mentions")

plt.ylabel("Company - Skill")

plt.tight_layout()

plt.savefig(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/outputs/charts/company_skill_counts.png",
    dpi=300
)

plt.show()