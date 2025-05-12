import logging

import boto3

logging.basicConfig(level=logging.INFO)


def upload_file_to_s3(
    file_name: str, bucket_name: str, object_name: str, region_name: str = "eu-north-1"
) -> None:
    """Uploads a file to S3 bucket."""

    try:
        client = boto3.client("s3", region_name=region_name)
        client.upload_file(file_name, bucket_name, object_name)
        logging.info(f"Frame uploaded to S3 bucket {bucket_name} as {object_name}")

    except Exception as e:
        logging.info(f"Frame not uploaded to S3 bucket: {e}")
