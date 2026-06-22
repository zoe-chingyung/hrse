###############################################################################
# HRSE – Terraform Root Module
#
# Provisions the AWS infrastructure required for the Household Resource
# Scheduling Engine. Business-logic resources (DynamoDB tables, EventBridge
# rules, etc.) will be added in Sprint 2.
###############################################################################

terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.55"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Replace bucket/key/region with your real state backend values.
  # Leave commented out for local development.
  # backend "s3" {
  #   bucket         = "my-terraform-state-bucket"
  #   key            = "hrse/terraform.tfstate"
  #   region         = "eu-west-2"
  #   encrypt        = true
  #   dynamodb_table = "terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "hrse"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

###############################################################################
# Lambda deployment package
###############################################################################

data "archive_file" "lambda_package" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda_packages/hrse"
  output_path = "${path.module}/../lambda_packages/hrse.zip"
}

###############################################################################
# Modules
###############################################################################

module "schedule_lambda" {
  source = "./modules/lambda"

  function_name    = "hrse-schedule-handler-${var.environment}"
  description      = "HRSE schedule lifecycle handler"
  handler          = "hrse.handlers.schedule_handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_package.output_path
  source_code_hash = data.archive_file.lambda_package.output_base64sha256

  environment_variables = {
    HRSE_AWS_REGION          = var.aws_region
    HRSE_SCHEDULE_TABLE_NAME = "hrse-schedules-${var.environment}"
    HRSE_LOG_LEVEL           = var.log_level
    HRSE_ENABLE_OPTIMISER    = "false"
    POWERTOOLS_SERVICE_NAME  = "hrse-schedule-handler"
    POWERTOOLS_LOG_LEVEL     = var.log_level
  }

  tags = {
    Component = "schedule-handler"
  }
}
