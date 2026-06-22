output "function_arn" {
  description = "ARN of the created Lambda function."
  value       = aws_lambda_function.this.arn
}

output "function_name" {
  description = "Name of the created Lambda function."
  value       = aws_lambda_function.this.function_name
}

output "role_arn" {
  description = "ARN of the Lambda execution IAM role."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Name of the Lambda execution IAM role (for policy attachment)."
  value       = aws_iam_role.this.name
}

output "log_group_name" {
  description = "Name of the CloudWatch log group."
  value       = aws_cloudwatch_log_group.this.name
}
