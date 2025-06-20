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

resource "aws_s3_bucket" "income_bucket" {
  bucket = var.input_bucket
}

resource "aws_s3_bucket" "processed_bucket" {
  bucket = var.processed_bucket
}

data "aws_s3_bucket" "models_bucket" {
  bucket = var.models_bucket
}

resource "aws_sqs_queue" "upload_events" {
  name                       = "qla-upload-events"
  visibility_timeout_seconds = 35
}

resource "aws_s3_bucket_notification" "income_notifications" {
  bucket = aws_s3_bucket.income_bucket.id

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
          "aws:SourceArn" = aws_s3_bucket.income_bucket.arn
        }
      }
    }]
  })
}

# DynamoDB Table
resource "aws_dynamodb_table" "image_metadata" {
  name         = var.db_table
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
          "${aws_s3_bucket.income_bucket.arn}",
          "${aws_s3_bucket.income_bucket.arn}/*",
          "${aws_s3_bucket.processed_bucket.arn}",
          "${aws_s3_bucket.processed_bucket.arn}/*"
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
        Action   = ["logs:*"],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "sagemaker:CreateTransformJob",
          "sagemaker:DescribeTransformJob",
        ],
        Resource = aws_sagemaker_model.object_detection_model.arn
        Resource = "arn:aws:sagemaker:${var.region}:${var.aws_account_id}:transform-job/*"
      },
      {
        Effect = "Allow",
        Action = [
          "iam:PassRole"
        ],
        Resource = aws_iam_role.sagemaker_execution_role.arn
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
          "s3:ListBucket",
        ],
        Resource = [
          "${aws_s3_bucket.income_bucket.arn}",
          "${aws_s3_bucket.income_bucket.arn}/*",
          "${aws_s3_bucket.processed_bucket.arn}",
          "${aws_s3_bucket.processed_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ],
        Resource = aws_dynamodb_table.image_stats.arn
      },
      {
        Effect = "Allow",
        Action = [
          "ecr:GetAuthorizationToken"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ],
        Resource = "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/${var.lambda2_image}"
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
}
resource "aws_lambda_function" "lambda1" {
  filename         = local.lambda1_zip_path
  function_name    = var.lambda1
  role             = aws_iam_role.lambda1_exec_role.arn
  handler          = "modules.lambda1.lambda_handler"
  runtime          = "python3.10"
  timeout          = 20
  source_code_hash = filebase64sha256(local.lambda1_zip_path)
  environment {
    variables = {
      TF_VAR_db_table         = var.db_table
      TF_VAR_input_bucket     = var.input_bucket
      TF_VAR_processed_bucket = var.processed_bucket
      TF_VAR_obj_det_model    = var.obj_det_model
    }
  }
}

# SQS Trigger for Lambda 1
resource "aws_lambda_event_source_mapping" "sqs_to_lambda1" {
  event_source_arn = aws_sqs_queue.upload_events.arn
  function_name    = aws_lambda_function.lambda1.arn
  batch_size       = 1
  enabled          = true
}


data "aws_ecr_image" "latest_lambda2_image" {
  repository_name = var.lambda2_image
  image_tag       = "latest"
}


# Lambda 2: summary function
resource "aws_lambda_function" "lambda2" {
  function_name = var.lambda2
  role          = aws_iam_role.lambda2_exec_role.arn
  package_type  = "Image"
  image_uri     = data.aws_ecr_image.latest_lambda2_image.image_uri
  timeout       = 20
  environment {
    variables = {
      TF_VAR_input_bucket       = var.input_bucket
      TF_VAR_processed_bucket   = var.processed_bucket
      TF_VAR_db_img_stats_table = var.db_img_stats_table
    }
  }
}


resource "aws_iam_role" "sagemaker_execution_role" {
  name = "sagemaker-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        },
        Effect = "Allow",
        Sid    = ""
      }
    ]
  })
}

resource "aws_iam_role_policy" "sagemaker_execution_policy" {
  name = "sagemaker-execution-policy"
  role = aws_iam_role.sagemaker_execution_role.name

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
        ],
        Resource = [
          "${aws_s3_bucket.income_bucket.arn}",
          "${aws_s3_bucket.income_bucket.arn}/*",
          "${aws_s3_bucket.processed_bucket.arn}",
          "${aws_s3_bucket.processed_bucket.arn}/*",
          "${data.aws_s3_bucket.models_bucket.arn}",
          "${data.aws_s3_bucket.models_bucket.arn}/*",
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "ecr:GetAuthorizationToken"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ],
        Resource = "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/${var.obj_det_image}"
      },
      {
        Effect   = "Allow",
        Action   = ["logs:*"],
        Resource = "*"
      }
    ]
  })
}

data "aws_ecr_image" "latest_obj_det_image" {
  repository_name = var.obj_det_image
  image_tag       = "latest"
}


resource "aws_sagemaker_model" "object_detection_model" {
  name               = var.obj_det_model
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  primary_container {
    image          = data.aws_ecr_image.latest_obj_det_image.image_uri
    model_data_url = "s3://${data.aws_s3_bucket.models_bucket.bucket}/model_ul/model.tar.gz"
  }
}

resource "aws_cloudwatch_event_rule" "sagemaker_job_completed" {
  name        = "sagemaker-transform-job-complete"
  description = "Trigger Lambda when SageMaker batch transform job completes"

  event_pattern = jsonencode({
    source        = ["aws.sagemaker"],
    "detail-type" = ["SageMaker Transform Job State Change"],
    detail = {
      TransformJobStatus = ["Completed", "Failed", "Stopped"]
    }
  })
}

resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.sagemaker_job_completed.name
  target_id = "SendToLambda"
  arn       = aws_lambda_function.lambda2.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.lambda2.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sagemaker_job_completed.arn
}

resource "aws_dynamodb_table" "image_stats" {
  name         = var.db_img_stats_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"
  range_key    = "category_name"

  attribute {
    name = "id"
    type = "S"
  }

  attribute {
    name = "category_name"
    type = "S"
  }
}

# IAM Role for EC2
resource "aws_iam_role" "ec2_instance_role" {
  name = "dash-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "ec2.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "ec2_policy" {
  name = "dash-ec2-access"
  role = aws_iam_role.ec2_instance_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ],
        Resource = "arn:aws:ecr:${var.region}:${var.aws_account_id}:repository/${var.dash_image}"
      },
      {
        Effect = "Allow",
        Action = [
          "ecr:GetAuthorizationToken"
        ],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ],
        Resource = [
          "${aws_s3_bucket.processed_bucket.arn}",
          "${aws_s3_bucket.processed_bucket.arn}/*",
        ]
      },
      {
        Effect = "Allow",
        Action = [
          "dynamodb:Scan",
        ],
        Resource = aws_dynamodb_table.image_stats.arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_instance_profile" {
  name = "dash-instance-profile"
  role = aws_iam_role.ec2_instance_role.name
}

# Security Group
resource "aws_security_group" "dash_sg" {
  name        = "dash-sg"
  description = "Allow HTTP traffic"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 8050
    to_port     = 8050
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Get Latest Amazon Linux 2 AMI
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-x86_64-gp2"]
  }
}

# Get Default VPC
data "aws_vpc" "default" {
  default = true
}

# EC2 Instance
resource "aws_instance" "dash_instance" {
  ami                    = data.aws_ami.amazon_linux.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.dash_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_instance_profile.name

  user_data = templatefile("${path.module}/startup.sh.tpl", {
    region          = var.region
    aws_account_id  = var.aws_account_id
    dash_image      = var.dash_image
  })

  tags = {
    Name = "dash-app"
  }
}

# Allocate a new Elastic IP
resource "aws_eip" "dash_eip" {
  tags = {
    Name = "dash-app-eip"
  }
}

# Associate the Elastic IP with our EC2 instance
resource "aws_eip_association" "eip_assoc" {
  instance_id   = aws_instance.dash_instance.id
  allocation_id = aws_eip.dash_eip.id
}

# scheduling EC2 instance start/stop using Lambda and EventBridge
# 1. IAM Role and Policy for Lambda to manage EC2
resource "aws_iam_role" "lambda_ec2_scheduler_role" {
  name = "lambda_ec2_scheduler_role"

  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "lambda_ec2_scheduler_policy" {
  name        = "lambda_ec2_scheduler_policy"
  description = "Allows Lambda to start/stop a specific EC2 instance and write logs."

  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow",
        Action   = ["ec2:StartInstances", "ec2:StopInstances"],
        Resource = aws_instance.dash_instance.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ec2_scheduler_attachment" {
  role       = aws_iam_role.lambda_ec2_scheduler_role.name
  policy_arn = aws_iam_policy.lambda_ec2_scheduler_policy.arn
}

# 2. Package Lambda functions from local files
data "archive_file" "start_instance_zip" {
  type        = "zip"
  source_file = "${path.module}/../modules/start_ec2.py"
  output_path = "${path.module}/../cloud_resources/start_ec2.zip"
}

data "archive_file" "stop_instance_zip" {
  type        = "zip"
  source_file = "${path.module}/../modules/stop_ec2.py"
  output_path = "${path.module}/../cloud_resources/stop_ec2.zip"
}

# 3. Define the Lambda Functions
resource "aws_lambda_function" "start_instance_lambda" {
  function_name = "start-dash-instance"
  filename      = data.archive_file.start_instance_zip.output_path
  handler       = "start_ec2.handler"
  runtime       = "python3.10"
  role          = aws_iam_role.lambda_ec2_scheduler_role.arn
  source_code_hash = data.archive_file.start_instance_zip.output_base64sha256

  environment {
    variables = {
      INSTANCE_ID = aws_instance.dash_instance.id
      REGION      = var.region
    }
  }
}

resource "aws_lambda_function" "stop_instance_lambda" {
  function_name = "stop-dash-instance"
  filename      = data.archive_file.stop_instance_zip.output_path
  handler       = "stop_ec2.handler"
  runtime       = "python3.10"
  role          = aws_iam_role.lambda_ec2_scheduler_role.arn
  source_code_hash = data.archive_file.stop_instance_zip.output_base64sha256

  environment {
    variables = {
      INSTANCE_ID = aws_instance.dash_instance.id
      REGION      = var.region
    }
  }
}

# 4. Create EventBridge Schedules to trigger the Lambdas
# Note: cron expressions are in UTC. "0 10 * * ? *" is 10:00 AM UTC.

resource "aws_scheduler_schedule" "start_ec2_daily" {
  name       = "start-dash-instance-daily-10am"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 10 ? * MON-FRI *)"
  schedule_expression_timezone = "Europe/Berlin"
  
  # The schedule will cease to run after this date.
  end_date = "2025-07-31T23:59:59Z"

  target {
    arn      = aws_lambda_function.start_instance_lambda.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda_role.arn
  }
}

resource "aws_scheduler_schedule" "stop_ec2_daily" {
  name       = "stop-dash-instance-daily-4pm"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 16 ? * MON-FRI *)" # 10 AM + 6 hours = 4 PM (16:00)
  schedule_expression_timezone = "Europe/Berlin"

  end_date = "2025-07-31T23:59:59Z"

  target {
    arn      = aws_lambda_function.stop_instance_lambda.arn
    role_arn = aws_iam_role.scheduler_invoke_lambda_role.arn
  }
}

# 5. IAM Role for the Scheduler to invoke Lambda
resource "aws_iam_role" "scheduler_invoke_lambda_role" {
  name = "scheduler_invoke_lambda_role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = {
        Service = "scheduler.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "scheduler_invoke_lambda_policy" {
  name = "scheduler_invoke_lambda_policy"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = [
        aws_lambda_function.start_instance_lambda.arn,
        aws_lambda_function.stop_instance_lambda.arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_invoke_lambda_attachment" {
  role       = aws_iam_role.scheduler_invoke_lambda_role.name
  policy_arn = aws_iam_policy.scheduler_invoke_lambda_policy.arn
}