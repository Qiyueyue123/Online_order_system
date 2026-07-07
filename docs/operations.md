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

## Continuous deployment

`.github/workflows/deploy.yml` builds and pushes the API image on every push to `main`, then
renders a new ECS task definition revision pinned to the commit SHA and deploys it (rather than
forcing a redeploy against whatever `:latest` resolves to at pull time). Each deploy is therefore
auditable and has a task-definition revision to roll back to.

Both jobs are gated on the `DEPLOY_ENABLED` repository variable so forks and clones without AWS
credentials configured don't get a red X on every push. Set `DEPLOY_ENABLED=true` (Settings >
Secrets and variables > Actions > Variables) once the `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` secrets are populated; leave it unset or `false` to disable the workflow
entirely.

## Enabling HTTPS

The demo environment serves plain HTTP by default. Set the `domain_name` Terraform variable to
request an ACM certificate and add an HTTPS listener on port 443; the port 80 listener then
redirects to HTTPS instead of forwarding traffic directly. Set `hosted_zone_id` as well to have
Terraform create the Route53 DNS validation records automatically; leave it empty to validate the
certificate manually (Terraform outputs the DNS records to create).

## Reservation sweeper

A background task in the API process periodically reconciles expired stock reservations. Its
interval is controlled by `RESERVATION_SWEEP_INTERVAL_SECONDS` (default `300`); setting it to `0`
disables the sweeper entirely, which is useful in tests and short-lived environments where no
background task should be running.

## Logging and request correlation

Set `JSON_LOGS=true` to emit one JSON object per log line, suitable for log aggregators; the
default is a human-readable format for local development. Every request is tagged with an
`X-Request-ID` header — either echoed back from an incoming request or generated as a UUID — and
the same ID is attached to that request's access log line, making it possible to correlate a
client-visible request with its corresponding log entries.
