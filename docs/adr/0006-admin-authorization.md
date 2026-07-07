# ADR 0006: Admin authorization and audit logging

Status: accepted

Admin capability is a set of `/api/v1/admin/*` endpoints gated by a server-side role check
on the session (`admin_session` dependency), with every admin mutation writing an
`admin_audit_log` row (actor, action, entity, detail) in the same transaction as the change
it records.

Decisions and reasons:

- **Role on the user, checked server-side, per request.** The frontend hides the admin UI
  from non-admins, but that is presentation only; authorization lives exclusively in the
  API. A hidden button is not a security control.
- **Simple two-role model (customer/admin), not full RBAC.** One shop, one operator; a
  role/permission matrix would be speculative complexity. The role column and the dependency
  pattern give a clean upgrade path to finer-grained roles if the team ever grows.
- **Audit log in the same transaction.** If the mutation commits, its audit row commits;
  neither can exist without the other. An async/best-effort audit trail can silently lose
  the one record an investigation needs.
- **Explicit state machine for order transitions.** Only `paid → fulfilled`,
  `pending_payment → cancelled`, and `paid → refunded` are permitted; anything else is 409.
  Cancellation releases reserved stock through the same helper the expiry sweeper uses, so
  the two release paths cannot drift apart.
- **Refunds are demo-only status flips.** A real refund must be executed at Stripe and
  confirmed by webhook before local state changes (consistent with ADR 0004: Stripe is
  payment truth). The endpoint documents this boundary rather than pretending.
- **Idempotent bootstrap, no default credentials.** `ADMIN_EMAIL`/`ADMIN_PASSWORD` seed a
  create-or-promote step; unset means no admin is created. There is no hardcoded admin and
  registration can never yield an admin role.
