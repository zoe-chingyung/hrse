###############################################################################
# HRSE – Telegram Bot Lambda + API Gateway HTTP API
#
# Sprint 2A: Telegram webhook receiver.
#
# Architecture:
#   Telegram → HTTPS POST → API Gateway HTTP API (route: POST /webhook)
#              → Lambda integration → telegram_handler.handler
###############################################################################

###############################################################################
# Secrets Manager – reference only (secret created out-of-band)
#
# The secret "hrse/dev/telegram" must be created manually (or via a separate
# bootstrap script) before deploying. Terraform reads its ARN so it can grant
# the Lambda permission to read it.
###############################################################################

data "aws_secretsmanager_secret" "telegram" {
  name = "hrse/${var.environment}/telegram"
}

###############################################################################
# IAM – Secrets Manager read policy (attached to the Lambda module's role)
###############################################################################

data "aws_iam_policy_document" "telegram_secrets" {
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

resource "aws_iam_policy" "telegram_secrets" {
  name        = "hrse-telegram-secrets-${var.environment}"
  description = "Allow hrse-telegram-handler to read the Telegram bot secret"
  policy      = data.aws_iam_policy_document.telegram_secrets.json
}

resource "aws_iam_role_policy_attachment" "telegram_secrets" {
  role       = module.telegram_lambda.role_name
  policy_arn = aws_iam_policy.telegram_secrets.arn
}

###############################################################################
# Lambda
###############################################################################

module "telegram_lambda" {
  source = "./modules/lambda"

  function_name    = "hrse-telegram-handler-${var.environment}"
  description      = "HRSE Telegram webhook handler"
  handler          = "hrse.handlers.telegram_handler.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_package.output_path
  source_code_hash = data.archive_file.lambda_package.output_base64sha256

  environment_variables = {
    HRSE_AWS_REGION           = "eu-west-2"
    HRSE_TELEGRAM_SECRET_NAME = "hrse/${var.environment}/telegram"
    HRSE_STATE_BUCKET_NAME    = "hrse-${var.environment}-state"
    HRSE_LOG_LEVEL            = var.log_level
    POWERTOOLS_SERVICE_NAME   = "hrse-telegram-handler"
    POWERTOOLS_LOG_LEVEL      = var.log_level
  }

  tags = {
    Component = "telegram-handler"
  }
}

###############################################################################
# API Gateway HTTP API
###############################################################################

resource "aws_apigatewayv2_api" "telegram_webhook" {
  name          = "hrse-telegram-webhook-${var.environment}"
  protocol_type = "HTTP"
  description   = "HRSE Telegram webhook endpoint"

  tags = {
    Component = "telegram-apigw"
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.telegram_webhook.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.apigw.arn

    # This must be inside the block and assigned a string value
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }
}

resource "aws_cloudwatch_log_group" "apigw" {
  name              = "/aws/apigateway/hrse-telegram-${var.environment}"
  retention_in_days = 30
}

###############################################################################
# Lambda integration + permission
###############################################################################

resource "aws_apigatewayv2_integration" "telegram_lambda" {
  api_id                 = aws_apigatewayv2_api.telegram_webhook.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.telegram_lambda.function_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "webhook_post" {
  api_id    = aws_apigatewayv2_api.telegram_webhook.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.telegram_lambda.id}"
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.telegram_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.telegram_webhook.execution_arn}/*/*/webhook"
}
