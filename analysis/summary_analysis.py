import pandas as pd
import ast

df = pd.read_csv(
    "/Users/shashank/Documents/Projects/ai-job-market-dashboard/data/processed/jobs_with_skills.csv"
)

df["skills"] = df["skills"].apply(ast.literal_eval)