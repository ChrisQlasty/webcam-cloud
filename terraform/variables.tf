variable "region" {
  default = "eu-north-1"
}

variable "aws_account_id" {
  type = string
}

variable "input_bucket" {
  type = string
}

variable "processed_bucket" {
  type = string
}

variable "models_bucket" {
  type = string
}

variable "obj_det_image" {
  type = string
}

variable "lambda2_image" {
  type = string
}

variable "lambda1" {
  type = string
}

variable "lambda2" {
  type = string
}

variable "db_table" {
  type = string
}

variable "db_img_stats_table" {
  type = string
}

variable "obj_det_model" {
  type = string
}

variable "budget_limit" {
  description = "Monthly budget limit in USD"
  default     = 10
}


variable "dash_image" {
  description = "The name of the ECR repo for dash app where your Docker image is stored."
  type        = string
}

variable "instance_type" {
  default = "t3.micro"
}

variable "key_name" {
  description = "Name of your EC2 key pair"
  default     = "my-ec2-keypair"
  type        = string
}