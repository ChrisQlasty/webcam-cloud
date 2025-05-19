import json
from datetime import datetime

import boto3

s3 = boto3.client("s3")

# SOURCE_BUCKET = "qla-income"
DEST_BUCKET = "qla-processed"


def lambda_handler(event, context):
    batch = event.get("batch", [])
    print(f"Batch received: {batch}")

    # You can either process the passed keys, or list entire bucket:
    # response = s3.list_objects_v2(Bucket=SOURCE_BUCKET)
    # files = [obj["Key"] for obj in response.get("Contents", [])]

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    manifest_key = f"batch-manifests/image_list_{timestamp}.json"

    s3.put_object(
        Bucket=DEST_BUCKET,
        Key=manifest_key,
        Body=json.dumps(batch),
        ContentType="application/json",
    )

    return {"statusCode": 200, "body": f"Processed batch: {batch}"}
