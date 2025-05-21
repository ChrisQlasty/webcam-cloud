import json
import os
import uuid

import boto3

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

BATCH_SIZE = 2
TABLE_NAME = os.getenv("TF_VAR_db_table")
BATCH_RUNNER_NAME = os.getenv("TF_VAR_lambda2")
SOURCE_BUCKET = os.getenv("TF_VAR_input_bucket")
DEST_BUCKET = os.getenv("TF_VAR_processed_bucket")

table = dynamodb.Table(TABLE_NAME)


def call_j():
    sagemaker = boto3.client("sagemaker")

    job_name = f"object-detection-job-{uuid.uuid4().hex[:8]}"
    sagemaker.create_transform_job(
        TransformJobName=job_name,
        ModelName="object-detection-model",
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
        TransformResources={"InstanceType": "ml.m5.large", "InstanceCount": 1},
    )

    return {"status": "Transform job started", "job_name": job_name}


def lambda_handler(event, context):
    print(event)
    for record in event.get("Records", []):
        print(record["body"])
        s3_event = json.loads(record["body"])
        s3_key = s3_event["Records"][0]["s3"]["object"]["key"]
        print(f"Adding key to batch: {s3_key}")

        # Append key to the batch (atomic update)
        response = table.update_item(
            Key={"batch_id": "current"},
            UpdateExpression="SET images = list_append(if_not_exists(images, :empty), :new)",
            ExpressionAttributeValues={":new": [s3_key], ":empty": []},
            ReturnValues="ALL_NEW",
        )

        images = response["Attributes"]["images"]
        print(f"Current batch: {images}")

        # If batch is full, invoke next Lambda and reset
        if len(images) == BATCH_SIZE:
            print("Batch full.")
            # print("Batch full. Invoking batch runner...")
            # lambda_client.invoke(
            #     FunctionName=BATCH_RUNNER_NAME,
            #     InvocationType="Event",  # async
            #     Payload=json.dumps({"batch": images}),
            # )

            # Reset batch
            table.put_item(Item={"batch_id": "current", "images": []})
            return call_j()

    return {"statusCode": 200}
