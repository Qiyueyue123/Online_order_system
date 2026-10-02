variable "aws_region" {
  type    = string
  default = "ap-southeast-1"
}

variable "project_name" {
  type    = string
  default = "matcha-demo"
}

variable "alert_email" {
  type = string
}

variable "monthly_budget_usd" {
  type    = number
  default = 60
}

variable "database_password" {
  type      = string
  sensitive = true
}

variable "ses_sender" {
  type = string
}

variable "domain_name" {
  type        = string
  default     = ""
  description = "Domain name to request an ACM certificate for and serve the API over HTTPS. Leave empty (default) to keep the ALB on plain HTTP with no ACM/Route53 resources created."
}

variable "hosted_zone_id" {
  type        = string
  default     = ""
  description = "Route53 hosted zone ID used to create DNS validation records for the ACM certificate. Leave empty to skip automatic validation and instead output the records for manual DNS setup."
}
