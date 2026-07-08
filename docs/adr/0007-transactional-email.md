# ADR 0007: Transactional order-confirmation email

Status: accepted

An order that transitions to `paid` (Stripe webhook, or the demo payment endpoint in
non-production) should email the customer a plain-text receipt.

Decisions and reasons:

- **Pluggable backend, console by default.** `EMAIL_BACKEND=console` logs the full
  message through the app logger (visible in `docker compose logs api`) and is the
  default so no local setup is required. `EMAIL_BACKEND=smtp` sends over plain
  `smtplib` (no TLS) to a local Mailpit container, added to docker-compose for
  browsing sent mail during development.
- **Send after the transaction commits, never inside it.** A slow SMTP call inside
  the transaction would hold row locks; a send followed by a rollback would confirm
  an order that never happened. Both call sites (`stripe_webhook`,
  `complete_demo_payment`) commit and refresh the order first, then send.
- **At-most-once, best-effort delivery.** Only one email is sent per order, gated on
  the request actually performing the `pending_payment -> paid` transition (a webhook
  replay that no-ops must not resend). A crash between commit and send loses the
  email with no retry — acceptable for a demo store, not for production. A send
  failure is caught and logged, never raised: the HTTP response and the webhook's
  200/204 must not depend on mail delivery, or Stripe will retry and the payment
  side will re-process (already guarded, but retries should not be provoked by an
  unrelated mail outage).
- **Production upgrade path.** Durable delivery needs a transactional outbox table
  (row written in the same commit as the order transition, drained by a separate
  worker) or a provider with its own queue and retries (SES, Resend) driven off that
  outbox — not a send call embedded in the request path.
- **Plain text only.** No HTML templates yet; the receipt is a formatted text body
  covering line items, subtotal/shipping/discount/total, and shipping address.
