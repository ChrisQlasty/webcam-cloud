terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_budgets_budget" "monthly_budget" {
  name              = "MonthlyBudget"
  budget_type       = "COST"
  time_unit         = "MONTHLY"
  limit_amount      = var.budget_limit
  limit_unit        = "USD"
  time_period_start = "2025-05-18_00:01"
}

resource "aws_s3_bucket" "qla_income" {
  bucket = "qla-income"
}

resource "aws_s3_bucket" "qla_processed" {
  bucket = "qla-processed"
}

resource "aws_sqs_queue" "upload_events" {
  name                       = "qla-upload-events"
  visibility_timeout_seconds = 35
}

resource "aws_s3_bucket_notification" "income_notifications" {
  bucket = aws_s3_bucket.qla_income.id

  queue {
    queue_arn     = aws_sqs_queue.upload_events.arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = ""
    filter_suffix = ".jpg"
  }
}

# Allow S3 to send messages to SQS
resource "aws_sqs_queue_policy" "s3_to_sqs" {
  queue_url = aws_sqs_queue.upload_events.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = "*"
      Action    = "SQS:SendMessage"
      Resource  = aws_sqs_queue.upload_events.arn
      Condition = {
        ArnLike = {
          "aws:SourceArn" = aws_s3_bucket.qla_income.arn
        }
      }
    }]
  })
}

# DynamoDB Table
resource "aws_dynamodb_table" "image_metadata" {
  name         = "qla_image_metadata"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "batch_id"

  attribute {
    name = "batch_id"
    type = "S"
  }
}

# Lambda Execution Role for lambda 1
resource "aws_iam_role" "lambda1_exec_role" {
  name = "qla_lambda1_exec_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Principal = {
        Service = "lambda.amazonaws.com"
      },
      Effect = "Allow",
      Sid    = ""
    }]
  })
}
# Lambda Execution Role for lambda 2
resource "aws_iam_role" "lambda2_exec_role" {
  name = "qla_lambda2_exec_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Principal = {
        Service = "lambda.amazonaws.com"
      },
      Effect = "Allow",
      Sid    = ""
    }]
  })
}

# IAM Policy for Lambda 1
resource "aws_iam_role_policy" "lambda1_policy" {
  name = "qla_lambda1_policy"
  role = aws_iam_role.lambda1_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ],
        Resource = [
          "${aws_s3_bucket.qla_income.arn}",
          "${aws_s3_bucket.qla_income.arn}/*",
          "${aws_s3_bucket.qla_processed.arn}",
          "${aws_s3_bucket.qla_processed.arn}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ],
        Resource = aws_dynamodb_table.image_metadata.arn
      },
      {
        Effect = "Allow",
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ],
        Resource = aws_sqs_queue.upload_events.arn
      },
      {
        Effect   = "Allow",
        Action   = "lambda:InvokeFunction",
        Resource = aws_lambda_function.lambda2.arn
      },
      {
        Effect   = "Allow",
        Action   = ["logs:*"],
        Resource = "*"
      }
    ]
  })
}
# IAM Policy for Lambda 2
resource "aws_iam_role_policy" "lambda2_policy" {
  name = "qla_lambda2_policy"
  role = aws_iam_role.lambda2_exec_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
        ],
        Resource = [
          "${aws_s3_bucket.qla_income.arn}",
          "${aws_s3_bucket.qla_income.arn}/*",
          "${aws_s3_bucket.qla_processed.arn}",
          "${aws_s3_bucket.qla_processed.arn}/*"
        ]
      },
      {
        Effect   = "Allow",
        Action   = ["logs:*"],
        Resource = "*"
      }
    ]
  })
}

# Lambda 1: triggered by SQS
locals {
  lambda1_zip_path = "${path.module}/../cloud_resources/lambda1.zip"
  lambda2_zip_path = "${path.module}/../cloud_resources/lambda2.zip"
}
resource "aws_lambda_function" "lambda1" {
  filename         = local.lambda1_zip_path
  function_name    = "qla_ingest_lambda"
  role             = aws_iam_role.lambda1_exec_role.arn
  handler          = "lambda1.lambda_handler"
  runtime          = "python3.11"
  timeout          = 20
  source_code_hash = filebase64sha256(local.lambda1_zip_path)
}

# SQS Trigger for Lambda 1
resource "aws_lambda_event_source_mapping" "sqs_to_lambda1" {
  event_source_arn = aws_sqs_queue.upload_events.arn
  function_name    = aws_lambda_function.lambda1.arn
  batch_size       = 1
  enabled          = true
}

# Lambda 2: summary function
resource "aws_lambda_function" "lambda2" {
  filename         = local.lambda2_zip_path # ZIP containing your Lambda 2 handler
  function_name    = "qla_summary_lambda"
  role             = aws_iam_role.lambda2_exec_role.arn
  handler          = "lambda2.lambda_handler"
  runtime          = "python3.11"
  timeout          = 20
  source_code_hash = filebase64sha256(local.lambda2_zip_path)
}


# resource "aws_lambda_permission" "allow_cloudwatch_to_invoke_lambda2" {
#   statement_id  = "AllowExecutionFromCloudWatch"
#   action        = "lambda:InvokeFunction"
#   function_name = aws_lambda_function.lambda2.function_name
#   principal     = "events.amazonaws.com"
#   source_arn    = aws_cloudwatch_event_rule.every_hour.arn
# }
