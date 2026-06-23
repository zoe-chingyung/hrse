###############################################################################
# HRSE – Household State S3 Bucket
#
# Sprint 2B: Event Memory Layer.
#
# Stores household activity events as JSON in S3.
# Bucket name pattern: hrse-{environment}-state
###############################################################################

###############################################################################
# S3 bucket
###############################################################################

resource "aws_s3_bucket" "hrse_state" {
  bucket = "hrse-${var.environment}-state"

  tags = {
    Component = "event-store"
  }
}

resource "aws_s3_bucket_versioning" "hrse_state" {
  bucket = aws_s3_bucket.hrse_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "hrse_state" {
  bucket = aws_s3_bucket.hrse_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "hrse_state" {
  bucket = aws_s3_bucket.hrse_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

###############################################################################
# IAM – least-privilege S3 policy for the Telegram Lambda
###############################################################################

data "aws_iam_policy_document" "state_s3" {
  statement {
    sid    = "AllowEventStoreReadWrite"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.hrse_state.arn}/events/*"]
  }

  statement {
    sid     = "AllowBucketList"
    effect  = "Allow"
    actions = ["s3:ListBucket"]
    resources = [aws_s3_bucket.hrse_state.arn]
  }
}

resource "aws_iam_policy" "state_s3" {
  name        = "hrse-state-s3-${var.environment}"
  description = "Allow hrse-telegram-handler to read/write household events in S3"
  policy      = data.aws_iam_policy_document.state_s3.json
}

resource "aws_iam_role_policy_attachment" "state_s3" {
  role       = module.telegram_lambda.role_name
  policy_arn = aws_iam_policy.state_s3.arn
}
