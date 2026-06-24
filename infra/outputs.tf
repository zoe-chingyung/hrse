###############################################################################
# Outputs
###############################################################################

output "schedule_lambda_arn" {
  description = "ARN of the schedule handler Lambda function."
  value       = module.schedule_lambda.function_arn
}

output "schedule_lambda_name" {
  description = "Name of the schedule handler Lambda function."
  value       = module.schedule_lambda.function_name
}

output "telegram_lambda_arn" {
  description = "ARN of the Telegram webhook handler Lambda function."
  value       = module.telegram_lambda.function_arn
}

output "telegram_webhook_url" {
  description = "URL to register with Telegram setWebhook. Format: POST https://api.telegram.org/bot<TOKEN>/setWebhook?url=<this_value>"
  value       = "${aws_apigatewayv2_stage.default.invoke_url}webhook"
}

output "state_bucket_name" {
  description = "Name of the S3 bucket used for household event storage."
  value       = aws_s3_bucket.hrse_state.id
}

output "daily_planning_rule_arn" {
  description = "ARN of the 16:45 UTC EventBridge rule (DailyPlanning)."
  value       = aws_cloudwatch_event_rule.daily_planning.arn
}

output "morning_reminder_rule_arn" {
  description = "ARN of the 08:00 UTC EventBridge rule (MorningReminder)."
  value       = aws_cloudwatch_event_rule.morning_reminder.arn
}
