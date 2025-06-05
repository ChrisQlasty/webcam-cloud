import io
import json
import logging
import os
import re
from datetime import datetime
from decimal import Decimal

import boto3
import numpy as np
import pandas as pd
from PIL import Image

from utils.aws_cloud import mv_files_to_bucket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


SOURCE_BUCKET = os.getenv("TF_VAR_input_bucket")
DEST_BUCKET = os.getenv("TF_VAR_processed_bucket")
DEST_TABLE = os.getenv("TF_VAR_db_img_stats_table")
UNPROCESSED_FOLDER = "unprocessed"
PROCESSED_FOLDER = "processed"

WRITE_TO_DB = True

ALLOWED_CATEGORIES = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "bus",
    "truck",
]

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(DEST_TABLE)


def get_filename(filename: str) -> str:
    """Extract datetime from filename"""
    match = re.search(r"image_(\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2})", filename)
    if match:
        dt_string = match.group(1)
        dt_key = datetime.strptime(dt_string, "%Y-%m-%d_%H:%M:%S").isoformat(sep="_")
    else:
        raise ValueError("Datetime not found in filename")
    return dt_key


def load_json_from_s3(bucket: str, key: str):
    """Return decoded JSON content from S3."""
    json_obj = s3.get_object(Bucket=bucket, Key=key)
    json_content = json_obj["Body"].read().decode("utf-8")
    return json.loads(json_content)


def proc_json(metadata, dt_key):
    """Process predictions metadata and store aggregated data in DynamoDB"""
    logger.info("Processing JSON metadata")

    df = pd.DataFrame(metadata)
    agg_df = df.groupby("category_name").agg(
        {"category_id": "count", "area": "mean", "score": "mean"}
    )

    for cat_name, agg_cat_row in agg_df.iterrows():
        if cat_name in ALLOWED_CATEGORIES:
            item = {
                "id": dt_key,  # partition key
                "category_name": cat_name,
                "count": int(agg_cat_row["category_id"]),
                "mean_area": Decimal(str(agg_cat_row["area"])),
                "mean_score": Decimal(str(agg_cat_row["score"])),
            }
            if WRITE_TO_DB:
                logger.info(f"Writing item to {DEST_TABLE} table: {item}")
                table.put_item(Item=item)


def load_jpeg_from_s3(bucket: str, key: str) -> np.ndarray:
    """Return image as numpy array from S3 JPEG."""
    jpeg_obj = s3.get_object(Bucket=bucket, Key=key)
    image_bytes = jpeg_obj["Body"].read()
    image_stream = io.BytesIO(image_bytes)
    return np.array(Image.open(image_stream))


def proc_jpeg(image: np.ndarray, dt_key: str):
    """Process image and calculate mean brightness, store in DynamoDB"""
    logger.info("Processing JPEG image")

    brightness = image.mean()

    item = {
        "id": dt_key,  # partition key
        "category_name": "whole_image",
        "mean_brightness": Decimal(str(brightness)),
    }
    if WRITE_TO_DB:
        logger.info(f"Writing item to {DEST_TABLE} table: {item}")
        table.put_item(Item=item)


def feed_db_with_preds(bucket, prefix):
    """Feed DynamoDB table with predictions from S3"""
    logger.info(f"Feeding DynamoDB table {DEST_TABLE} with image statistics")
    output_files = {}
    paginator = s3.get_paginator("list_objects_v2")
    prefix = prefix.strip("/")
    prefix = f"{prefix}/" if prefix else ""
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            unique_id = os.path.basename(key).split(".")[0]

            if unique_id not in output_files:
                output_files[unique_id] = {}

            if key.endswith(".out"):
                output_files[unique_id]["json_key"] = key
            elif key.endswith(".jpg"):
                output_files[unique_id]["jpeg_key"] = key

    for unique_id, fv in output_files.items():
        dt_key = get_filename(unique_id)

        if "json_key" in fv:
            metadata = load_json_from_s3(bucket, fv["json_key"])
            proc_json(metadata, dt_key)

        if "jpeg_key" in fv:
            image = load_jpeg_from_s3(bucket, fv["jpeg_key"])
            proc_jpeg(image, dt_key)


def lambda_handler(event, context):
    # move images files from source to unprocessed bucket after transform job completes
    mv_files_to_bucket(
        s3,
        source_bucket=SOURCE_BUCKET,
        dest_bucket=DEST_BUCKET,
        source_prefix="",
        dest_prefix=UNPROCESSED_FOLDER,
    )

    # feed DynamoDB table with predictions from S3 and image statistics
    feed_db_with_preds(bucket=DEST_BUCKET, prefix=UNPROCESSED_FOLDER)

    # move images & json files from unprocessed to processed bucket after basic info extraction completes
    mv_files_to_bucket(
        s3,
        source_bucket=DEST_BUCKET,
        dest_bucket=DEST_BUCKET,
        source_prefix=UNPROCESSED_FOLDER,
        dest_prefix=PROCESSED_FOLDER,
    )


if __name__ == "__main__":
    lambda_handler(None, None)
