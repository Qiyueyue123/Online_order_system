# External services and keys

Local browsing, accounts, carts, orders, PostgreSQL and simulated payment require no external
account. `docker compose up --build` migrates and seeds the local database before starting the API.

## Stripe test payments

Required only when replacing the built-in simulated payment page with Stripe Checkout.

1. Create or sign in to a Stripe account and switch to **Test mode**.
2. Copy the test secret key from Developers → API keys.
3. Install Stripe CLI, run `stripe login`, then:

   ```bash
   stripe listen --forward-to localhost:8001/api/v1/stripe/webhook
   ```

4. Put the values printed by Stripe into `apps/api/.env`:

   ```env
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

Never use an `sk_live_` key in this project. When using Docker Compose, add the same values to the
`api` service environment or an `env_file`.

## AWS deployment

Required only for a public cloud deployment. Local development does not use AWS credentials.

1. Create an AWS account with MFA and configure AWS CLI authentication using IAM Identity Center
   or a short-lived role. Do not create permanent root access keys.
2. Verify the intended sender identity in SES.
3. Copy `infra/environments/demo/terraform.tfvars.example` to
   `infra/environments/demo/terraform.tfvars` and set:

   - `alert_email`: receives budget warnings.
   - `database_password`: generated database secret.
   - `ses_sender`: the SES-verified address/domain.

4. From `infra/environments/demo`, run `terraform init`, `terraform plan`, and only then
   `terraform apply`.

The current Terraform baseline creates S3/CloudFront, ECR, ECS/ALB, RDS, Secrets Manager, SES,
logs and a budget. A real public release still needs a chosen domain, Route 53/ACM TLS wiring,
GitHub AWS OIDC deployment configuration and production secret replacement.

## Keys not needed yet

- No Google, Facebook or other social-login key: authentication is first-party.
- No database API key: PostgreSQL uses the local Docker credentials.
- No email key locally: email verification/reset delivery is not implemented yet.
- No S3 key locally: product media currently uses regular URLs; presigned upload is pending.
