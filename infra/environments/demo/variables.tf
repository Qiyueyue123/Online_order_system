variable "aws_region" { type = string; default = "ap-southeast-1" }
variable "project_name" { type = string; default = "matcha-demo" }
variable "alert_email" { type = string }
variable "monthly_budget_usd" { type = number; default = 60 }
variable "database_password" { type = string; sensitive = true }
variable "ses_sender" { type = string }
