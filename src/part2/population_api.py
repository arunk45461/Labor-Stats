"""
Part 2: Fetch US Population Data from DataUSA API and store in S3.
API: https://honolulu-api.datausa.io/tesseract/data.jsonrecords
Docs: https://datausa.io/about/api/
"""

import os
import json
import logging
from datetime import datetime

import boto3
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_URL = (
    "https://honolulu-api.datausa.io/tesseract/data.jsonrecords"
    "?cube=acs_yg_total_population_1"
    "&drilldowns=Year%2CNation"
    "&locale=en"
    "&measures=Population"
)

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "labor-stats-data")
S3_KEY = "population/us_population.json"

HEADERS = {
    "User-Agent": "LaborStatsProject/1.0 (contact@example.com)",
    "Accept": "application/json",
}


def fetch_population_data() -> dict:
    """Fetch population data from the DataUSA API."""
    logger.info(f"Fetching population data from: {API_URL}")
    response = requests.get(API_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    logger.info(f"Retrieved {len(data.get('data', []))} records")
    return data


def save_to_s3(data: dict) -> str:
    """Serialize data as JSON and write to S3. Returns the S3 URI."""
    s3 = boto3.client("s3")

    payload = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "source": API_URL,
        "data": data,
    }

    body = json.dumps(payload, indent=2)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=S3_KEY,
        Body=body.encode("utf-8"),
        ContentType="application/json",
    )

    s3_uri = f"s3://{S3_BUCKET}/{S3_KEY}"
    logger.info(f"Saved population data to {s3_uri}")
    return s3_uri


def fetch_and_store():
    """Fetch population data and save it to S3."""
    data = fetch_population_data()
    uri = save_to_s3(data)
    return {"s3_uri": uri, "record_count": len(data.get("data", []))}


def lambda_handler(event, context):
    """AWS Lambda entry point for Part 2."""
    result = fetch_and_store()
    return {"statusCode": 200, "body": result}


if __name__ == "__main__":
    result = fetch_and_store()
    print(result)
