import json
import logging
import os

import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

s3 = boto3.client("s3")

SOURCE_BUCKET = os.getenv("TF_VAR_input_bucket")
DEST_BUCKET = os.getenv("TF_VAR_processed_bucket")


def lambda_handler(event, context):
    try:
        job_name = event["detail"]["TransformJobName"]
        status = event["detail"]["TransformJobStatus"]

        logger.info(f"Job {job_name} completed with status: {status}")
    except KeyError as e:
        logger.info(e)

    # List files in source prefix
    response = s3.list_objects_v2(Bucket=SOURCE_BUCKET)
    if "Contents" not in response:
        logger.info(f"No files found in {SOURCE_BUCKET}")
        return {"statusCode": 200, "body": "No files to move."}

    for obj in response["Contents"]:
        src_key = obj["Key"]
        filename = src_key.split("/")[-1]
        dst_key = f"org_images/{filename}"

        logger.info(f"Moving {src_key} to {DEST_BUCKET}/{dst_key}")

        # Copy to destination
        s3.copy_object(
            Bucket=DEST_BUCKET,
            CopySource={"Bucket": SOURCE_BUCKET, "Key": src_key},
            Key=dst_key,
        )

        # Delete original
        s3.delete_object(Bucket=SOURCE_BUCKET, Key=src_key)

    # TODO: list output jsons, move add content to dynamodb and move the to new dir

    return {
        "statusCode": 200,
        "body": json.dumps(f"Moved files to {DEST_BUCKET}/org_images/"),
    }
