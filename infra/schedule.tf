###############################################################################
# HRSE – Sprint 4: Scheduled Notifications
#
# Provisions:
#   1. EventBridge rules — two cron schedules invoking the schedule Lambda:
#        - DailyPlanning  : 16:45 UTC daily (recommend for tomorrow)
#        - MorningReminder: 08:00 UTC daily (remind for today)
#   2. Lambda invoke permissions for EventBridge.
#   3. IAM policy granting the schedule Lambda read access to:
#        - The Telegram secret (bot_token + chat_id)
#        - The S3 state bucket (weekly summary events)
###############################################################################

###############################################################################
# EventBridge — Daily Planning (16:45 UTC)
###############################################################################

resource "aws_cloudwatch_event_rule" "daily_planning" {
  name                = "hrse-daily-planning-${var.environment}"
  description         = "Triggers HRSE schedule Lambda at 16:45 UTC to recommend tomorrow's laundry window"
  schedule_expression = "cron(45 16 * * ? *)"
  state               = "ENABLED"

  tags = {
    Component = "scheduler"
  }
}

resource "aws_cloudwatch_event_target" "daily_planning" {
  rule      = aws_cloudwatch_event_rule.daily_planning.name
  target_id = "hrse-schedule-lambda-planning"
  arn       = module.schedule_lambda.function_arn

  input = jsonencode({
    source        = "hrse.scheduler"
    "detail-type" = "DailyPlanning"
    detail        = {}
  })
}

resource "aws_lambda_permission" "daily_planning" {
  statement_id  = "AllowEventBridgeDailyPlanning"
  action        = "lambda:InvokeFunction"
  function_name = module.schedule_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_planning.arn
}

###############################################################################
# EventBridge — Morning Reminder (08:00 UTC)
###############################################################################

resource "aws_cloudwatch_event_rule" "morning_reminder" {
  name                = "hrse-morning-reminder-${var.environment}"
  description         = "Triggers HRSE schedule Lambda at 08:00 UTC to send today's laundry reminder"
  schedule_expression = "cron(0 8 * * ? *)"
  state               = "ENABLED"

  tags = {
    Component = "scheduler"
  }
}

resource "aws_cloudwatch_event_target" "morning_reminder" {
  rule      = aws_cloudwatch_event_rule.morning_reminder.name
  target_id = "hrse-schedule-lambda-reminder"
  arn       = module.schedule_lambda.function_arn

  input = jsonencode({
    source        = "hrse.scheduler"
    "detail-type" = "MorningReminder"
    detail        = {}
  })
}

resource "aws_lambda_permission" "morning_reminder" {
  statement_id  = "AllowEventBridgeMorningReminder"
  action        = "lambda:InvokeFunction"
  function_name = module.schedule_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_reminder.arn
}

###############################################################################
# IAM — Secrets Manager read (bot_token + chat_id)
###############################################################################

data "aws_iam_policy_document" "schedule_secrets" {
  statement {
    sid    = "ReadTelegramSecret"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [data.aws_secretsmanager_secret.telegram.arn]
  }
}

resource "aws_iam_policy" "schedule_secrets" {
  name        = "hrse-schedule-secrets-${var.environment}"
  description = "Allow hrse-schedule-handler to read the Telegram secret"
  policy      = data.aws_iam_policy_document.schedule_secrets.json
}

resource "aws_iam_role_policy_attachment" "schedule_secrets" {
  role       = module.schedule_lambda.role_name
  policy_arn = aws_iam_policy.schedule_secrets.arn
}

###############################################################################
# IAM — S3 state bucket read (weekly summary events)
###############################################################################

data "aws_iam_policy_document" "schedule_s3" {
  statement {
    sid    = "AllowEventStoreRead"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.hrse_state.arn}/events/*"]
  }

  statement {
    sid       = "AllowBucketList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.hrse_state.arn]
  }
}

resource "aws_iam_policy" "schedule_s3" {
  name        = "hrse-schedule-s3-${var.environment}"
  description = "Allow hrse-schedule-handler to read household events from S3"
  policy      = data.aws_iam_policy_document.schedule_s3.json
}

resource "aws_iam_role_policy_attachment" "schedule_s3" {
  role       = module.schedule_lambda.role_name
  policy_arn = aws_iam_policy.schedule_s3.arn
}
