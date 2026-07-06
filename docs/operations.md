# Operations

## Deployment order

1. Build and test API and web artifacts.
2. Run `alembic upgrade head` as a one-off ECS deployment task.
3. Deploy compatible API tasks and wait for healthy ALB targets.
4. Upload the versioned React build and invalidate CloudFront.
5. Smoke-test health, TLS, catalog, database access, media and Stripe test webhook delivery.

Migrations never run in the API container startup command.

## Rollback

Keep the prior immutable ECR tag and frontend build. Roll application artifacts back only when
the migration is backward compatible. For destructive schema changes, use expand/migrate/contract
across releases.

## Teardown

Empty versioned S3 buckets, disable deletion protection if enabled, then run
`terraform destroy` from `infra/environments/demo`. Confirm RDS snapshots and Secrets Manager
recovery windows before deletion. Budget notifications and retained logs may outlive compute.
