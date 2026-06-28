"""
Part 4: Combined Lambda handler for Part 1 + Part 2.
This single Lambda function runs both the BLS data sync and the
population API fetch. It is scheduled via EventBridge to run daily.
"""

import logging
import json

from part1.bls_sync import sync_bls_to_s3
from part2.population_api import fetch_and_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """
    Scheduled Lambda (EventBridge daily rule).
    Runs Part 1 (BLS sync) and Part 2 (population API) in sequence.
    """
    logger.info("Starting scheduled data pipeline run")

    # Part 1
    logger.info("--- Running Part 1: BLS Data Sync ---")
    bls_result = sync_bls_to_s3()
    logger.info(f"Part 1 result: {bls_result}")

    # Part 2
    logger.info("--- Running Part 2: Population API Fetch ---")
    pop_result = fetch_and_store()
    logger.info(f"Part 2 result: {pop_result}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "part1_bls_sync": bls_result,
            "part2_population": pop_result,
        }),
    }
