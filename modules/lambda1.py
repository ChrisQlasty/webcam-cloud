import json
import logging
import os
import uuid

import boto3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

BATCH_SIZE = 2
TABLE_NAME = os.getenv("TF_VAR_db_table")
SOURCE_BUCKET = os.getenv("TF_VAR_input_bucket")
DEST_BUCKET = os.getenv("TF_VAR_processed_bucket")
MODEL_NAME = os.getenv("TF_VAR_obj_det_model")
INSTANCE_TYPE = os.getenv("instance_type", "ml.m5.large")

table = dynamodb.Table(TABLE_NAME)


def call_batch_transform_job():
    sagemaker = boto3.client("sagemaker")

    job_name = f"object-detection-job-{uuid.uuid4().hex[:8]}"
    sagemaker.create_transform_job(
        TransformJobName=job_name,
        ModelName=MODEL_NAME,
        TransformInput={
            "DataSource": {
                "S3DataSource": {
                    "S3DataType": "S3Prefix",
                    "S3Uri": f"s3://{SOURCE_BUCKET}/",
                }
            },
            "ContentType": "application/x-image",
        },
        TransformOutput={
            "S3OutputPath": f"s3://{DEST_BUCKET}/",
            "Accept": "application/json",
        },
        TransformResources={"InstanceType": INSTANCE_TYPE, "InstanceCount": 1},
    )

    return {"status": "Transform job started", "job_name": job_name}


def lambda_handler(event, context):
    try:
        for record in event.get("Records", []):
            s3_event = json.loads(record["body"])
            s3_key = s3_event["Records"][0]["s3"]["object"]["key"]
            logger.info(f"Adding key to batch: {s3_key}")

            # Append key to the batch (atomic update)
            response = table.update_item(
                Key={"batch_id": "current"},
                UpdateExpression="SET images = list_append(if_not_exists(images, :empty), :new)",
                ExpressionAttributeValues={":new": [s3_key], ":empty": []},
                ReturnValues="ALL_NEW",
            )

            images = response["Attributes"]["images"]
            logger.info(f"Current batch: {images}")

            # If batch is full, invoke next Lambda and reset
            if len(images) == BATCH_SIZE:
                logger.info("Batch full.")

                # Reset batch
                table.put_item(Item={"batch_id": "current", "images": []})
                # TODO: trigger another Lambda when job is finished
                return call_batch_transform_job()
    except Exception as e:
        print(f"Error processing event: {e}")
        return {"statusCode": 500, "body": str(e)}

    return {"statusCode": 200}
