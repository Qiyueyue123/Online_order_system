# Payments: from demo to real money

The store currently runs in local demo mode (a simulator page instead of Stripe).
This is the staged plan for testing and going live. Do the stages in order; each one
is cheap to verify and hard to skip safely.

## Stage 0 — now (no accounts needed)

Pay-at-pickup covers the real dorm business immediately: orders are confirmed unpaid,
you collect cash/Swish/Revolut in person, and mark fulfilled in the admin. Nothing to
test beyond what CI already covers. You can run the café on this alone.

## Stage 1 — Stripe test mode (do when: you have 30 min; costs nothing)

1. Create a Stripe account (stripe.com — choose Sweden, SEK).
2. From the dashboard get the **test** keys (`sk_test_…`, and a webhook signing secret
   after step 4).
3. Locally: put `STRIPE_SECRET_KEY=sk_test_…` in `.env` — the API switches from the
   simulator to real Stripe-hosted test checkout automatically (the demo endpoint 404s
   when a Stripe key is configured).
4. Run `stripe listen --forward-to localhost:8001/api/v1/stripe/webhook` (Stripe CLI)
   and put the printed `whsec_…` in `.env` as `STRIPE_WEBHOOK_SECRET`.
5. Pay with test card `4242 4242 4242 4242` (any future expiry, any CVC). Verify:
   order goes paid **via the webhook** (kill the redirect tab before it loads to prove
   the webhook alone is sufficient), confirmation email sends once, stock consumed.
6. Test the failure paths: card `4000 0000 0000 9995` (declined), and abandon a
   checkout to watch the reservation expire via the sweeper.

## Stage 2 — deployed test mode (do when: the AWS deploy is live)

Same test keys, but in AWS Secrets Manager instead of `.env`, and a real webhook
endpoint configured in the Stripe dashboard (https://your-domain/api/v1/stripe/webhook).
Re-run the Stage 1 checklist against the deployed site. This proves TLS, DNS, and the
production webhook path — the things localhost can't.

## Stage 3 — live mode (do when: you're ready to take a real order)

1. Complete Stripe's business activation (identity, bank account for payouts).
2. Enable **Swish** in Stripe dashboard → Settings → Payment methods (SEK only —
   already our currency). Cards work with zero extra setup.
3. Swap to live keys (`sk_live_…`) in Secrets Manager; create the live-mode webhook.
4. Make ONE real purchase yourself (cheapest drink), verify the payout arrives in the
   bank account, then refund it from the Stripe dashboard.
5. Only then share the link publicly.

## Fees to know (Sweden, as of 2026 — verify current pricing)

- Stripe cards (EEA): ~1.5% + 1.80 kr per charge. On a 40 kr latte ≈ 2.40 kr.
- Stripe Swish: ~2.9% + fixed fee — compare with taking Swish person-to-person at
  pickup (free) before enabling it online.
- Pay-at-pickup: free. For a dorm café this is your margin-friendly default; online
  payment is the convenience option.

## What NOT to do

- Never put live keys in `.env`/git — Secrets Manager only.
- Never mark an order paid from the redirect page — the webhook stays the only
  source of payment truth (ADR 0004), in test and live alike.
