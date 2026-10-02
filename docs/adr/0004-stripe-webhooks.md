# ADR 0004: Stripe webhooks are payment truth

Status: accepted

Only a signature-verified Stripe event may transition an order to paid. Store event IDs for
idempotency. Success and cancellation redirects are presentation only. The release uses test
keys exclusively and labels every payment surface as a demonstration.
