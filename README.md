# Matcha Store

A full-stack e-commerce demonstration store for packaged matcha, built as a portfolio project
that shows the complete path from a beginner Flask prototype to a production-shaped system:
typed API contracts, transactional inventory, test-mode payments, infrastructure as code, and
CI that guards all of it.

**Stack:** FastAPI + SQLAlchemy 2.0 + PostgreSQL · React 19 + TypeScript + Vite · Stripe (test
mode) · Terraform on AWS (S3/CloudFront, ECS Fargate, RDS) · GitHub Actions CI/CD.

It charges SGD only and never accepts live payments. Taxes, import duties, returns automation,
and currency conversion are explicitly out of scope.

## Repository layout

| Path | What it is |
|---|---|
| `apps/api` | FastAPI backend: catalog, cart, checkout, orders, Stripe webhooks |
| `apps/web` | React storefront with types generated from the API's OpenAPI contract |
| `infra/` | Terraform: static site (S3+CloudFront), ECS/ALB/RDS demo environment, budget alarms |
| `docs/` | Architecture, operations, walkthrough, and five ADRs recording key decisions |
| `app/`, `run.py` | The original Flask/SQLite café — kept as a runnable v1 reference ([its full docs](docs/legacy-cafe.md)) |

## Highlights worth reading

- **Inventory that can't oversell** — checkout locks variant rows (`SELECT … FOR UPDATE`),
  reprices server-side (client prices are never trusted), reserves stock separately from
  on-hand stock, and writes an audit trail (`apps/api/app/services/checkout.py`).
- **Payments where the webhook is the source of truth** — only a signature-verified Stripe
  webhook can mark an order paid; redirect pages are presentation only. Events are recorded
  for idempotency ([ADR 0004](docs/adr/0004-stripe-webhooks.md)).
- **Opaque server-side sessions** — random tokens stored as SHA-256 hashes, httponly cookies,
  CSRF via double-submit header; JWTs deliberately rejected ([ADR 0001](docs/adr/0001-opaque-sessions.md)).
- **A contract the compiler enforces** — the frontend's API types are generated from
  `openapi.json`; CI fails if the committed contract drifts from the code, and the frontend
  fails to compile if it drifts from the contract ([ADR 0002](docs/adr/0002-rest-contract.md)).

## Quick start

Prerequisites: Docker (simplest), or Python 3.12 + Node 22 for the manual path.

```bash
docker compose up --build
```

Compose runs migrations and an idempotent seed before starting the API. Storefront:
`http://localhost:5173` · API docs: `http://localhost:8001/docs`.

Manual development setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
cd apps/web && npm install && cd ../..
docker compose up -d postgres
make migrate && make seed
make api    # terminal 1 — FastAPI on :8001
make web    # terminal 2 — Vite dev server on :5173
```

Useful commands:

```bash
make test       # legacy, API, and frontend suites
make lint       # ruff + eslint
make openapi    # regenerate the API contract + frontend type declarations
```

Docs: [architecture](docs/architecture.md) · [operations](docs/operations.md) ·
[walkthrough](docs/walkthrough.md) · [external services](docs/external-services.md) ·
[legacy café guide](docs/legacy-cafe.md).

## Session status — morning of 2026-07-08

Overnight autonomous session ended when the usage limit was reached (~4:30am reset).

**Landed and green in CI (PR #1, branch `qiyueclaude`)** — three waves, all five CI checks
passing after each: reservation sweeper, OpenAPI-derived frontend types, CI web lint/tests,
CD workflow, optional ALB HTTPS, observability middleware, checkout/auth frontend tests,
DB-backed rate limiting, dependabot, SEO metadata, docs updates. Details in the engineering
log below.

**Interrupted mid-work (uncommitted changes left in the working tree — review before
committing or discard with `git checkout -- .`):**
- Legacy hardening (`app/`, `tests/`): pickup-slot capacity race fix, SQLite
  `PRAGMA foreign_keys=ON`, CSRF test-bypass removal. Code partially written, tests not run.
- Compose smoke-test CI job (`.github/workflows/ci.yml`): partially written, not validated.
- API test gaps (webhook idempotency, coupons, cart merge): not started — no files written.

**To resume tomorrow:** finish/verify the three interrupted items, then remaining roadmap:
merge PR #1, enable `DEPLOY_ENABLED` + AWS secrets for CD, set `domain_name` for HTTPS,
provision Stripe test keys to the deployed environment.

**Permission-blocked items:** none — nothing was skipped for permissions this session.

## Engineering log

A running record of significant changes, what each one did, and why it matters. Newest first.

### 2026-07-07 (night) — Hardening wave

**Database-backed rate limiting** (`apps/api/app/services/rate_limit.py`, migration
`1c2f8a9d4e6b`). The auth rate limiter was an in-process dict — each Gunicorn worker or
Fargate replica had its own counter, so the real limit was `10 × number_of_processes` and
reset on every restart. Attempts are now recorded in a `rate_limit_events` table: one shared
counter no matter how many replicas, with stale events pruned on each check so the table
can't grow unboundedly. *Lesson: any state that must be enforced globally (rate limits,
sessions, locks) cannot live in process memory once you scale past one process.*

**Dependabot** (`.github/dependabot.yml`). Weekly grouped update PRs across all six
ecosystems in the repo (pip ×2, npm, GitHub Actions, Terraform, Docker). *Lesson: unpatched
dependencies are how most real sites get compromised; automation beats discipline.*

**Storefront SEO/metadata** (`apps/web/index.html`, `public/`). Title, meta description,
Open Graph/Twitter cards, SVG favicon, robots.txt, and a `<noscript>` fallback — the
difference between a link that unfurls properly when shared and a blank card.

**Docs updated** — `docs/operations.md` and `docs/architecture.md` now document the CD
workflow, HTTPS variables, sweeper knob, and request-ID log correlation.

### 2026-07-07 (evening) — Deployability and observability wave

**CD pipeline** (`.github/workflows/deploy.yml`). On every push to `main`: build the API
image, push to ECR tagged with the git SHA, then deploy by rendering a *new ECS task-definition
revision pinned to that exact image* — not `--force-new-deployment` on `:latest`, which would
redeploy "whatever latest happens to be" with no rollback trail. Gated behind a
`DEPLOY_ENABLED` repository variable so the workflow skips (grey, not red) until AWS
credentials are configured. *Lesson: deploys should be immutable and auditable — a SHA-pinned
revision is both a receipt and an undo button.*

**HTTPS for the API** (`infra/environments/demo`). The ALB previously spoke plain HTTP :80 —
the single biggest "not actually production" gap. Now setting `domain_name` provisions an ACM
certificate (DNS-validated, automatically if `hosted_zone_id` is given), a TLS 1.3 :443
listener, and converts :80 into a 301 redirect. With no domain set, behavior is unchanged, so
the config still applies for demo users. *Lesson: TLS terminates at the load balancer; the
cert is free (ACM) — the real work is DNS validation proving you own the domain.*

**Observability middleware** (`apps/api/app/observability.py`). Every response now carries an
`X-Request-ID` (accepted from the caller or generated), every request logs one structured
access line (method, path, status, duration), optionally as JSON (`JSON_LOGS=1`) for log
aggregators, and every response gets security headers (nosniff, frame-deny, referrer policy,
HSTS only under secure-cookie config). Implemented as pure ASGI middleware so streaming and
error responses are covered too. *Lesson: request IDs are the thread you pull when debugging
distributed systems — the ID in the user's error report finds the exact log lines.*

**Checkout and auth flow tests** (`apps/web`, 7 → 14 tests). The two riskiest user flows —
paying and signing in — now have tests covering validation, exact API payloads, redirects,
and error display. Along the way, a latent test-infrastructure bug: Testing Library's
automatic DOM cleanup silently never ran (it requires Vitest globals, which this project
doesn't enable), so DOM leaked between tests and could satisfy queries by accident. Explicit
`cleanup()` fixed it. *Lesson: a test suite that can pass by accident is worse than a smaller
honest one.*

**README restructured** — legacy café tutorial moved to `docs/legacy-cafe.md`; this file now
leads with what the project demonstrates.

### 2026-07-07 — First CI run, and everything it caught

**Reservation-expiry sweeper** (`apps/api/app/services/checkout.py`, `main.py`). Checkout
reserves stock and relies on Stripe's `checkout.session.expired` webhook to release it — but
webhooks are push-based and can never be the *only* mechanism (no Stripe configured = stock
reserved forever). Added `expire_stale_orders()`, an idempotent function that releases
reservations on pending orders past their deadline, driven by a background loop in the FastAPI
lifespan (`RESERVATION_SWEEP_INTERVAL_SECONDS`, default 300; `0` disables it for tests). The
DB work runs via `asyncio.to_thread` so it never blocks the event loop — async functions don't
make blocking code non-blocking. *Lesson: every webhook needs a reconciliation job backstop.*

**Frontend now consumes the generated OpenAPI types** (`apps/web/src/api/client.ts`). The types
were hand-copied duplicates of the contract; CI checked the contract but nothing forced the app
to obey it. Now `Product`, `Cart`, `Order` etc. are aliases into the generated
`components["schemas"]`, so a backend contract change breaks the frontend at compile time
instead of at runtime. Found on arrival: the hand-written types were *stricter* than the
contract (literal `"SGD"` vs `string`) — assumptions the backend never guaranteed.

**Real frontend tests** — jsdom + Testing Library wired into Vitest; catalog, cart, and API
error-handling tests replace a suite that previously covered only a currency formatter.

**CI actually guards the frontend** (`.github/workflows/ci.yml`) — the web job ran only
`npm run build`; lint and tests now run first. CI only proves what it runs.

**First-ever CI run: 3/5 green, and both failures were real.**
- *terraform job*: `variables.tf` used semicolons inside single-line HCL blocks — invalid
  syntax that had never been caught because Terraform had never been executed anywhere.
  Fixed to canonical multi-line blocks, then a second failure: `terraform fmt -check`
  enforces canonical *formatting* (like gofmt), fixed by running the formatter.
- *contract job*: the committed `openapi.json` was stale — the API code had grown a cart
  cookie parameter and orders endpoints that were never regenerated. The drift check did
  exactly its job on its first run. Fixed with `make openapi`.
- Bonus lesson: a local `terraform init` pulled a 648 MB provider binary into `.terraform/`
  which accidentally got committed — GitHub rejected the push (100 MB limit). `.terraform/`
  is local cache and is now gitignored; `.terraform.lock.hcl` (version + checksum pins, the
  `package-lock.json` of Terraform) *is* committed.

*The meta-lesson of the day: "works on my machine" only covers what's installed on your
machine. CI is the machine that never forgets to check.*

### Earlier — the v1 → v2 rewrite

The project began as a server-rendered Flask/SQLite café for a real ~50-user use case
(pickup slots, cash/Tikkie payment, admin dashboard) — see the
[legacy café guide](docs/legacy-cafe.md) for its full history and learning notes. The modern
stack was then designed around the questions the prototype couldn't answer: concurrent-safe
inventory, real payment flows, typed API contracts, repeatable infrastructure, and CI. The
five [ADRs](docs/adr/) record those decisions.

## Known limitations (deliberate scope)

- Demo/test payments only; no live Stripe keys, taxes, duties, or currency conversion.
- Single-AZ RDS and `desired_count = 1` — a documented cost tradeoff ([ADR 0005](docs/adr/0005-aws-topology.md)).
- Rate limiting is in-process (not distributed); observability is CloudWatch logs plus
  structured request logging.

## Notes

This README is updated as the project evolves; the engineering log above is the change record.
