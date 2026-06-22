variable "function_name" {
  description = "Unique name for the Lambda function."
  type        = string
}

variable "description" {
  description = "Human-readable description of the function."
  type        = string
  default     = ""
}

variable "handler" {
  description = "Module.function handler path, e.g. hrse.handlers.schedule_handler.handler."
  type        = string
}

variable "runtime" {
  description = "Lambda runtime identifier."
  type        = string
  default     = "python3.12"
}

variable "filename" {
  description = "Path to the deployment package ZIP."
  type        = string
}

variable "source_code_hash" {
  description = "Base64 SHA-256 of the deployment package (forces update on change)."
  type        = string
}

variable "environment_variables" {
  description = "Map of environment variables injected into the function."
  type        = map(string)
  default     = {}
}

variable "timeout_seconds" {
  description = "Function execution timeout in seconds."
  type        = number
  default     = 30
}

variable "memory_mb" {
  description = "Amount of memory allocated to the function (MB)."
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch log group retention period in days."
  type        = number
  default     = 30
}

variable "tags" {
  description = "Additional resource tags."
  type        = map(string)
  default     = {}
}
