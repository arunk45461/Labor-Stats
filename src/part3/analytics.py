"""
Part 3: Data Analytics
Loads BLS time-series data (Part 1) and population data (Part 2) from S3,
then generates three reports using Pandas.

Reports:
  1. Mean and standard deviation of US population (2013–2018 inclusive)
  2. Best year per series_id (year with max summed quarterly value)
  3. Join of PRS30006032 Q01 values with population for that year
"""

import io
import json
import logging
import os

import boto3
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "labor-stats-data")
BLS_KEY = "bls/pr/pr.data.0.Current"
POPULATION_KEY = "population/us_population.json"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_bls_data(s3_client) -> pd.DataFrame:
    """Load pr.data.0.Current from S3 into a DataFrame."""
    logger.info(f"Loading BLS data from s3://{S3_BUCKET}/{BLS_KEY}")
    obj = s3_client.get_object(Bucket=S3_BUCKET, Key=BLS_KEY)
    content = obj["Body"].read().decode("utf-8")

    df = pd.read_csv(
        io.StringIO(content),
        sep="\t",
        dtype=str,
    )

    # Strip whitespace from all string columns (BLS data has trailing spaces)
    df.columns = [c.strip() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].str.strip()

    df["year"] = df["year"].astype(int)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    logger.info(f"Loaded {len(df)} BLS records")
    return df


def load_population_data(s3_client) -> pd.DataFrame:
    """Load US population JSON from S3 into a DataFrame."""
    logger.info(f"Loading population data from s3://{S3_BUCKET}/{POPULATION_KEY}")
    obj = s3_client.get_object(Bucket=S3_BUCKET, Key=POPULATION_KEY)
    payload = json.loads(obj["Body"].read().decode("utf-8"))

    records = payload.get("data", payload)
    df = pd.DataFrame(records)

    # Normalise column names
    df.columns = [c.strip() for c in df.columns]

    # The API returns "Year" and "Population"
    if "Year" in df.columns:
        df.rename(columns={"Year": "year"}, inplace=True)
    if "Population" in df.columns:
        df.rename(columns={"Population": "population"}, inplace=True)

    df["year"] = df["year"].astype(int)
    df["population"] = pd.to_numeric(df["population"], errors="coerce")

    logger.info(f"Loaded {len(df)} population records")
    return df


# ---------------------------------------------------------------------------
# Report generators
# ---------------------------------------------------------------------------

def report_population_stats(pop_df: pd.DataFrame) -> dict:
    """
    Report 1: Mean and std-dev of US population for years 2013–2018 inclusive.
    """
    filtered = pop_df[(pop_df["year"] >= 2013) & (pop_df["year"] <= 2018)]
    mean_pop = filtered["population"].mean()
    std_pop = filtered["population"].std()

    result = {
        "years": "2013-2018",
        "record_count": len(filtered),
        "mean_population": round(mean_pop, 2),
        "std_population": round(std_pop, 2),
    }
    logger.info(f"[Report 1] Population stats 2013–2018: {result}")
    return result


def report_best_year_per_series(bls_df: pd.DataFrame) -> pd.DataFrame:
    """
    Report 2: For each series_id, find the year with the highest summed value
    across all quarters. Returns a DataFrame with columns:
      series_id | year | value
    """
    # Filter out annual rows (period == "Q05" is sometimes used for annual)
    quarterly = bls_df[bls_df["period"].str.startswith("Q")]

    # Sum values per series + year
    grouped = (
        quarterly
        .groupby(["series_id", "year"])["value"]
        .sum()
        .reset_index()
    )

    # Find the year with the max sum for each series_id
    idx = grouped.groupby("series_id")["value"].idxmax()
    best = grouped.loc[idx].reset_index(drop=True)
    best = best.rename(columns={"value": "summed_value"})

    logger.info(f"[Report 2] Best year per series — {len(best)} series found")
    logger.info(f"\n{best.head(10).to_string(index=False)}")
    return best


def report_prs30006032_with_population(
    bls_df: pd.DataFrame, pop_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Report 3: Filter BLS for series_id=PRS30006032 and period=Q01,
    then join with population data on year.

    NOTE: Whitespace trimming is applied before filtering (BLS data hint).
    """
    filtered = bls_df[
        (bls_df["series_id"] == "PRS30006032") &
        (bls_df["period"] == "Q01")
    ][["series_id", "year", "period", "value"]].copy()

    merged = filtered.merge(pop_df[["year", "population"]], on="year", how="left")
    merged = merged.sort_values("year").reset_index(drop=True)

    logger.info(f"[Report 3] PRS30006032 Q01 joined with population:")
    logger.info(f"\n{merged.to_string(index=False)}")
    return merged


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_analytics():
    """Execute all three analytics reports."""
    s3 = boto3.client("s3")

    bls_df = load_bls_data(s3)
    pop_df = load_population_data(s3)

    r1 = report_population_stats(pop_df)
    r2 = report_best_year_per_series(bls_df)
    r3 = report_prs30006032_with_population(bls_df, pop_df)

    return {
        "report1_population_stats": r1,
        "report2_best_year_per_series": r2.to_dict(orient="records"),
        "report3_prs30006032_q01": r3.to_dict(orient="records"),
    }


def lambda_handler(event, context):
    """AWS Lambda entry point for Part 3 (triggered by SQS)."""
    logger.info(f"SQS trigger received: {json.dumps(event)}")
    results = run_analytics()

    # Log the reports (Lambda CloudWatch logs capture this)
    logger.info("=== REPORT 1: Population Stats (2013–2018) ===")
    logger.info(json.dumps(results["report1_population_stats"], indent=2))

    logger.info("=== REPORT 2: Best Year Per Series (first 10) ===")
    for row in results["report2_best_year_per_series"][:10]:
        logger.info(row)

    logger.info("=== REPORT 3: PRS30006032 Q01 with Population ===")
    for row in results["report3_prs30006032_q01"]:
        logger.info(row)

    return {"statusCode": 200, "body": "Analytics complete. See CloudWatch logs."}


if __name__ == "__main__":
    run_analytics()
