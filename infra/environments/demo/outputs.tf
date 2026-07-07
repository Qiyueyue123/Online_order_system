output "storefront_bucket" { value = module.storefront.bucket_name }
output "api_repository_url" { value = aws_ecr_repository.api.repository_url }
output "database_endpoint" { value = aws_db_instance.postgres.address }
output "storefront_domain" { value = module.storefront.distribution_domain }
output "api_load_balancer" { value = aws_lb.api.dns_name }
output "alb_dns_name" { value = aws_lb.api.dns_name }

output "acm_validation_records" {
  description = "DNS records to create manually to validate the ACM certificate when hosted_zone_id is not set."
  value = local.https_enabled && var.hosted_zone_id == "" ? [
    for dvo in aws_acm_certificate.api[0].domain_validation_options : {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  ] : []
}
