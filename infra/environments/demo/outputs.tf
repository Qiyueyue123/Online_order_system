output "storefront_bucket" { value = module.storefront.bucket_name }
output "api_repository_url" { value = aws_ecr_repository.api.repository_url }
output "database_endpoint" { value = aws_db_instance.postgres.address }
output "storefront_domain" { value = module.storefront.distribution_domain }
output "api_load_balancer" { value = aws_lb.api.dns_name }
