# Architecture

The modern store lives beside the unchanged Flask application. PostgreSQL is the modern
system of record; the legacy SQLite data is intentionally not migrated.

```mermaid
flowchart LR
  Browser[React storefront] -->|HTTPS /api/v1 + secure cookies| ALB[FastAPI]
  ALB --> Service[Application services]
  Service --> DB[(PostgreSQL)]
  Service --> S3[(S3 media)]
  Service --> Stripe[Stripe test mode]
  Stripe -->|signed, idempotent webhook| ALB
  Service --> SES[SES email]
```

Dependency direction is HTTP routes → application services → domain rules → SQLAlchemy
repositories/database. The HTTP layer never accepts authoritative price or total fields.

## Checkout data flow

```mermaid
sequenceDiagram
  participant R as React
  participant A as FastAPI
  participant P as PostgreSQL
  participant S as Stripe
  R->>A: POST /checkout (address, coupon)
  A->>P: lock variants; validate stock, shipping, coupon
  A->>P: create pending order + snapshots + reservations
  A->>S: create test Checkout Session with order_id metadata
  A-->>R: checkout URL
  S->>A: signed checkout.session.completed
  A->>P: record event; consume reservation; mark paid
```

The webhook event identifier is stored in `processed_webhooks` in the same transaction as
the state change. Duplicate delivery is a no-op. A browser redirect cannot mark an order paid.

## Observability

Every HTTP request passes through ASGI middleware that assigns (or propagates) a request ID,
returns it as the `X-Request-ID` response header, and emits a structured access log line tagged
with that ID, the route, status and duration. A second middleware adds standard security response
headers on every response, including ones raised from exception handlers.

## Reservation sweep as reconciliation backstop

Per ADR 0004, only a signature-verified Stripe webhook may mark an order paid — the webhook is the
single source of payment truth. A background sweeper independently reconciles the other side of
that boundary: it periodically releases stock reservations attached to orders that never reached
a paid state, so an abandoned or failed checkout doesn't hold stock indefinitely. It does not
grant payment authority; it only cleans up reservations once they expire.

## Glossary

- **Available stock:** on-hand units minus units held by active reservations.
- **Reservation:** a bounded stock hold attached to a pending order.
- **Snapshot:** immutable name, SKU and price copied onto an order item.
- **Guest lookup token:** a high-entropy secret whose hash is stored with a guest order.
- **Opaque session:** a random revocable token; identity and role remain server-side.
