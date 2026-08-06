import pandas as pd
import matplotlib.pyplot as plt

# -----------------------------
# Load Dataset
# -----------------------------

df = pd.read_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/raw/jobs_master.csv"
)

print(f"Dataset Shape: {df.shape}")
print()

# -----------------------------
# Company Analysis
# -----------------------------

company_counts = (
    df.groupby("company")
      .size()
      .reset_index(name="Jobs Posted")
)

company_counts = company_counts.sort_values(
    by="Jobs Posted",
    ascending=False
)

print(company_counts)

# -----------------------------
# Save Results
# -----------------------------

company_counts.to_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/company_counts.csv",
    index=False
)

print("\nSaved company_counts.csv")

# -----------------------------
# Visualization
# -----------------------------

top10 = company_counts.head(10)

plt.figure(figsize=(10,6))

plt.barh(top10["company"], top10["Jobs Posted"])

plt.gca().invert_yaxis()

plt.title("Top Companies by Number of Job Openings")

plt.xlabel("Number of Jobs")

plt.ylabel("Company")

plt.tight_layout()

plt.savefig(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/outputs/charts/company_counts.png",
    dpi=300
)

plt.show()