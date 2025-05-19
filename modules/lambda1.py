import json

import boto3

dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

TABLE_NAME = "qla_image_metadata"
BATCH_SIZE = 4
BATCH_RUNNER_NAME = "qla_summary_lambda"

table = dynamodb.Table(TABLE_NAME)


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
            print("Batch full. Invoking batch runner...")
            lambda_client.invoke(
                FunctionName=BATCH_RUNNER_NAME,
                InvocationType="Event",  # async
                Payload=json.dumps({"batch": images}),
            )

            # Reset batch
            table.put_item(Item={"batch_id": "current", "images": []})

    return {"statusCode": 200}
