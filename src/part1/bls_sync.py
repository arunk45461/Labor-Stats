"""
Part 1: BLS Data Sync to S3
Fetches data from https://download.bls.gov/pub/time.series/pr/
and syncs it to an S3 bucket.

BLS 403 Fix: User-Agent header with contact info is required per BLS policy:
https://www.bls.gov/bls/pss.htm
"""

import os
import hashlib
import logging
import boto3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BLS_BASE_URL = "https://download.bls.gov/pub/time.series/pr/"
S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "labor-stats-data")
S3_PREFIX = "bls/pr/"

# IMPORTANT FIX: BLS blocks requests without a proper User-Agent.
# Per BLS policy (https://www.bls.gov/bls/pss.htm), robots must include
# contact information so BLS can reach the owner. Without this header
# you will receive 403 Forbidden errors.
HEADERS = {
    "User-Agent": "LaborStatsProject/1.0 (contact@example.com)"
}


def get_s3_client():
    return boto3.client("s3")


def list_bls_files():
    """Scrape the BLS directory listing and return all file URLs."""
    logger.info(f"Fetching BLS directory listing from {BLS_BASE_URL}")
    response = requests.get(BLS_BASE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    files = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Skip parent directory links and navigation
        if href.startswith("?") or href == "/" or href.startswith("/pub"):
            continue
        if href and not href.startswith("http"):
            full_url = urljoin(BLS_BASE_URL, href)
            files.append((href.strip("/"), full_url))

    logger.info(f"Found {len(files)} files in BLS directory")
    return files


def get_file_md5(content: bytes) -> str:
    """Compute MD5 hash of file content."""
    return hashlib.md5(content).hexdigest()


def get_s3_etag(s3_client, bucket: str, key: str) -> str | None:
    """Get the ETag (MD5) of an existing S3 object."""
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        return response["ETag"].strip('"')
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return None
        raise


def list_s3_files(s3_client, bucket: str, prefix: str) -> set:
    """List all file keys currently in S3 under the given prefix."""
    keys = set()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def sync_bls_to_s3():
    """
    Main sync function:
    1. Lists all files from BLS website
    2. Downloads each file
    3. Skips upload if file already exists with same content (MD5 check)
    4. Deletes S3 files that no longer exist on BLS
    """
    s3 = get_s3_client()
    bls_files = list_bls_files()
    bls_file_names = {name for name, _ in bls_files}

    # Track current S3 state
    existing_s3_keys = list_s3_files(s3, S3_BUCKET, S3_PREFIX)
    existing_s3_names = {
        key.replace(S3_PREFIX, "") for key in existing_s3_keys
    }

    uploaded = 0
    skipped = 0
    deleted = 0

    # Upload new/changed files
    for file_name, file_url in bls_files:
        s3_key = f"{S3_PREFIX}{file_name}"

        logger.info(f"Downloading {file_url}")
        response = requests.get(file_url, headers=HEADERS, timeout=60)
        response.raise_for_status()
        content = response.content

        local_md5 = get_file_md5(content)
        remote_etag = get_s3_etag(s3, S3_BUCKET, s3_key)

        if remote_etag == local_md5:
            logger.info(f"  SKIP (unchanged): {file_name}")
            skipped += 1
            continue

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType="text/plain",
            Metadata={"md5": local_md5},
        )
        logger.info(f"  UPLOADED: {file_name}")
        uploaded += 1

    # Delete files removed from BLS source
    for s3_name in existing_s3_names:
        if s3_name and s3_name not in bls_file_names:
            s3_key = f"{S3_PREFIX}{s3_name}"
            s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
            logger.info(f"  DELETED (removed from source): {s3_name}")
            deleted += 1

    logger.info(
        f"Sync complete. Uploaded: {uploaded}, Skipped: {skipped}, Deleted: {deleted}"
    )
    return {
        "uploaded": uploaded,
        "skipped": skipped,
        "deleted": deleted,
    }


def lambda_handler(event, context):
    """AWS Lambda entry point for Part 1."""
    result = sync_bls_to_s3()
    return {"statusCode": 200, "body": result}


if __name__ == "__main__":
    sync_bls_to_s3()
