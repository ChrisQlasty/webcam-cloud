#!/bin/bash

# 1. Define Variables
ROLE_NAME="lambda-yt-analytics-role"
ACCOUNT_ID=$AWS_ACCOUNT_ID
BUCKET_NAME=$ENV_BUCKET_NAME


# 2. Create the IAM Role
aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document file://aws_configs/trust-policy.json

# 3. Attach Basic Execution Policy
aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole


# 5. Create IAM Policy
POLICY_ARN=$(aws iam create-policy --policy-name "lambda-s3-policy-$BUCKET_NAME" --policy-document file://aws_configs/s3-policy.json --query 'Policy.Arn' --output text)

# 6. Attach the Custom S3 Policy
aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn "$POLICY_ARN"

# 7. Get the Role ARN
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)

echo "Lambda Role ARN: $ROLE_ARN"