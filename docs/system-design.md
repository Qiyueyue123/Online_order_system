# System design, as demonstrated by this repo

An interview-preparation tour. Each section is a standard system-design interview topic,
what this project actually does about it, and where the code lives. The strongest interview
answers are grounded in something you built — use these.

## 1. Start with requirements and scale honestly

Interviews start with "clarify requirements," and this repo embodies why: the legacy Flask
app (`app/`) was designed for ~50 users with cash payments — SQLite, one process,
server-rendered HTML — and those were the *right* choices at that scale. The modern stack
exists because the requirements changed (concurrent checkouts, card payments, deployability).

**Interview line:** "I sized the v1 for its real load — SQLite and a single container — and
rebuilt when requirements outgrew it. Overengineering v1 would have been the mistake."

## 2. Data modeling and the source of truth

`apps/api/app/models.py`: normalized relational schema — Product → Variant (the sellable
unit with price and stock), Order → OrderItem (which *snapshots* name and price at purchase
time, so later catalog edits can't rewrite history), InventoryMovement as an append-only
audit trail.

Key idea: **stock is two numbers, not one** — `stock_on_hand` and `stock_reserved`.
Available = on_hand − reserved. A pending checkout reserves; payment consumes; expiry
releases. One column can't distinguish "sold" from "promised."

## 3. Concurrency: the double-booking problem

The classic interview question ("two users buy the last item simultaneously") appears twice
here, solved two ways:

- **Modern API** (`apps/api/app/services/checkout.py`): pessimistic row locking —
  `SELECT … FOR UPDATE` on the variant rows inside the checkout transaction. Second
  transaction blocks until the first commits, then re-reads and fails cleanly.
- **Legacy app** (`app/db.py`): SQLite `BEGIN IMMEDIATE` — a coarse whole-database write
  lock. Cruder, but correct at its scale. (A slot-capacity check that *wasn't* inside the
  transaction was a real race bug we found and fixed — capacity was validated before the
  lock, so two orders could both pass and overbook the slot.)

**Interview line:** "Validation done outside the transaction is a suggestion, not a
guarantee. The check must happen under the same lock that the write takes."

## 4. Distributed operations: payments and reconciliation

Stripe checkout is a distributed transaction across two systems that can't share one
database. This repo's answers (ADR 0004):

- **The webhook is the only source of payment truth.** Browser redirect pages are
  presentation; only a signature-verified `checkout.session.completed` event marks an order
  paid.
- **Idempotency**: every processed event id is recorded (`ProcessedWebhook`); replaying an
  event is a no-op. Webhooks are delivered at-least-once, so handlers must tolerate repeats.
- **Reconciliation backstop**: webhooks can be lost, so a periodic sweeper
  (`expire_stale_orders`) releases reservations whose deadline passed. Push (webhooks) plus
  pull (sweep) — never push alone.

**Interview line:** "At-least-once delivery means idempotent handlers; push notifications
need a reconciliation job as a backstop."

## 5. Statelessness and horizontal scaling

The API is stateless: sessions live in the database (hashed opaque tokens, ADR 0001), carts
live in the database, so any replica can serve any request — the precondition for scaling
`desired_count` beyond 1.

We hit the classic violation of this in real form: the auth rate limiter was an in-process
dict, so N replicas meant N separate counters (effective limit ×N, reset on restart). Fix:
counters moved to the shared database (`rate_limit_events`).

**Interview line:** "Anything enforced globally — rate limits, sessions, locks — must live
in shared state, not process memory. Process memory is per-replica by definition."

## 6. Caching and content delivery

Two-tier delivery (ADR 0005, `infra/`): static frontend on S3 behind CloudFront (cached at
edge, HTTPS, origin locked down via OAC so the bucket is never public), dynamic API behind
an ALB. This is the standard "static goes to CDN, dynamic goes to compute" split, and it's
also a cost story: CloudFront serves the heavy assets so the single Fargate task only does
API work.

## 7. Availability vs. cost (know your tradeoffs)

Deliberate single-AZ RDS and one API task (ADR 0005) — a documented cost decision for a
demo. The upgrade path is equally documentable: multi-AZ RDS (synchronous standby,
automatic failover), `desired_count ≥ 2` across AZs behind the ALB, autoscaling on CPU or
request count. Interviewers care less about which you chose than whether you can name the
tradeoff and the migration path.

## 8. API contracts as a system boundary

The OpenAPI contract (`apps/api/openapi.json`) is generated from code, committed, and CI
fails when it drifts; the frontend's types are generated *from* it, so a breaking API change
fails compilation, not production (ADR 0002). This is consumer-driven-contract thinking in
a two-service system — the same idea that keeps microservice fleets from breaking each other.

## 9. Delivery pipeline as architecture

Deploys are immutable and auditable: each merge builds an image tagged with the git SHA and
deploys a new ECS task-definition revision pinned to it (`.github/workflows/deploy.yml`).
Rollback = redeploy the previous revision. Nothing deploys `:latest`, because "latest" is a
moving target that can't be rolled back to.

## 10. Observability

You can't operate what you can't see: every response carries an `X-Request-ID` (accepted or
generated), every request logs one structured line with duration, optionally as JSON for log
aggregators (`apps/api/app/observability.py`). The request id is the correlation key that
turns "a user saw an error" into "these exact log lines."

## 11. Security in layers

- Passwords: Argon2 (memory-hard, GPU-resistant), never reversible hashes.
- Sessions: random opaque tokens stored only as SHA-256 hashes — a database leak doesn't
  leak usable sessions; revocation is a row delete (why JWTs were rejected, ADR 0001).
- CSRF: double-submit token compared with `secrets.compare_digest`.
- Transport: HTTPS at the edges (CloudFront; ACM + 443 listener on the ALB), HSTS header.
- Headers: nosniff, frame-deny, referrer policy on every response.
- Rate limiting on auth endpoints; secrets in AWS Secrets Manager, never in git.

**Interview line:** "No single control is the answer; each layer assumes another failed."

## 12. Authorization: the admin plane

The admin capability ([ADR 0006](adr/0006-admin-authorization.md)) demonstrates the
authorization questions interviewers probe:

- **Where does authorization live?** Only in the API (`admin_session` dependency on every
  `/admin` route, 401/403 tested for each). The UI hiding admin pages is UX, not security —
  say this sentence in the interview and you're ahead of most candidates.
- **How much RBAC?** Two roles, because one shop has one operator. Name the upgrade path
  (role→permissions table) instead of building it — right-sizing is the skill being tested.
- **Why an audit log, and why synchronous?** Every admin mutation writes who/what/when *in
  the same transaction*, so the audit row and the change commit or roll back together.
  Compliance frameworks (SOC 2, GDPR) fundamentally ask "who had access and what did they
  do" — an async audit trail that can drop writes fails that question precisely when it
  matters.
- **State machines over booleans.** Order status transitions are an explicit allowlist
  (paid→fulfilled, pending→cancelled, paid→refunded; else 409). Invalid states become
  unrepresentable instead of "we validate in the UI."

## 13. The testing pyramid, deployed

Unit/service tests (checkout invariants, sweeper idempotency), contract tests (OpenAPI
drift), frontend component tests (Testing Library), and an end-to-end compose smoke test in
CI that boots postgres + migrations + seed + API + storefront and curls through the stack.
Fast tests catch logic; the smoke test catches integration ("does it actually boot").

---

### How to use this in an interview

When asked "design an e-commerce checkout," walk the actual path: reserve stock under a row
lock → create pending order with expiry → redirect to payment → webhook (verified,
idempotent) marks paid and consumes reservation → sweeper reconciles abandonments. Then
scale it: stateless API replicas, shared-state rate limits, CDN for static, multi-AZ when
availability justifies cost. Every step of that answer is a file in this repo.
