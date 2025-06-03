import json
from typing import Any

import boto3

from utils.loggers import create_logger

logger = create_logger(__name__)


def upload_file_to_s3(
    file_name: str, bucket_name: str, object_name: str, region_name: str = "eu-north-1"
) -> None:
    """Uploads a file to S3 bucket."""

    try:
        client = boto3.client("s3", region_name=region_name)
        client.upload_file(file_name, bucket_name, object_name)
        logger.info(f"Frame uploaded to S3 bucket {bucket_name} as {object_name}")

    except Exception as e:
        logger.info(f"Frame not uploaded to S3 bucket: {e}")


def mv_files_to_bucket(
    s3: Any,
    source_bucket: str,
    dest_bucket: str,
    source_prefix: str = "",
    dest_prefix: str = "",
) -> dict:
    """Move all files to target bucket"""

    source_prefix = source_prefix.strip("/")
    dest_prefix = dest_prefix.strip("/")

    # List files in source bucket
    response = s3.list_objects_v2(
        Bucket=source_bucket, Prefix=f"{source_prefix}/" if source_prefix else ""
    )
    if "Contents" not in response:
        logger.info(f"No files found in {source_bucket}")
        return {"statusCode": 200, "body": "No files to move."}

    for obj in response["Contents"]:
        src_key = obj["Key"]
        filename = src_key.split("/")[-1]
        dst_key = f"{dest_prefix}/{filename}" if dest_prefix else filename

        logger.info(f"Moving {src_key} to {dest_bucket}/{dst_key}")

        # Copy to destination
        s3.copy_object(
            Bucket=dest_bucket,
            CopySource={"Bucket": source_bucket, "Key": src_key},
            Key=dst_key,
        )

        # Delete original
        s3.delete_object(Bucket=source_bucket, Key=src_key)

    return {
        "statusCode": 200,
        "body": json.dumps(f"Moved files to {dest_bucket}/{dest_prefix}"),
    }
