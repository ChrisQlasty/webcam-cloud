import json
import os
from datetime import datetime

import boto3

s3 = boto3.client("s3")

# SOURCE_BUCKET = "qla-income"
DEST_BUCKET = os.getenv("TF_VAR_processed_bucket")


def lambda_handler(event, context):
    batch = event.get("batch", [])
    batch = [img_name.replace("%3A", ":") for img_name in batch]
    print(f"Batch received: {batch}")

    # You can either process the passed keys, or list entire bucket:
    # response = s3.list_objects_v2(Bucket=SOURCE_BUCKET)
    # files = [obj["Key"] for obj in response.get("Contents", [])]

    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    manifest_key = f"batch-manifests/image_list_{timestamp}.json"

    s3.put_object(
        Bucket=DEST_BUCKET,
        Key=manifest_key,
        Body=json.dumps(batch),
        ContentType="application/json",
    )

    return {"statusCode": 200, "body": f"Processed batch: {batch}"}
