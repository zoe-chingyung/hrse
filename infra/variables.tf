###############################################################################
# Input variables
###############################################################################

variable "aws_region" {
  description = "AWS region to deploy resources into."
  type        = string
  default     = "eu-west-2"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "log_level" {
  description = "Lambda log level (DEBUG | INFO | WARNING | ERROR)."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of: DEBUG, INFO, WARNING, ERROR."
  }
}

variable "invite_code" {
  description = "Shared invite code /start <code> must match to register a new chat (Sprint A). No default — must be set explicitly, e.g. in a gitignored terraform.tfvars."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.invite_code) > 0
    error_message = "invite_code must be set (non-empty) — see terraform.tfvars.example."
  }
}
