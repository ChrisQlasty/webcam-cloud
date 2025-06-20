import os

import boto3


def handler(event, context):
    instance_id = os.environ["INSTANCE_ID"]
    region = os.environ["REGION"]
    ec2 = boto3.client("ec2", region_name=region)

    print(f"Starting instance: {instance_id}")
    ec2.start_instances(InstanceIds=[instance_id])

    return {"statusCode": 200, "body": f"Successfully started instance {instance_id}"}
