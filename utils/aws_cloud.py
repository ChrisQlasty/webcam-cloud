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
