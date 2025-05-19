variable "region" {
  default = "eu-north-1"
}

variable "aws_account_id" {
  type = string
}

variable "budget_limit" {
  description = "Monthly budget limit in USD"
  default     = 10
}